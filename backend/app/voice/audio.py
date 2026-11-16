"""Identify an uploaded audio clip by its bytes and measure its duration, in memory only.

The declared content type is never trusted on its own: the container is sniffed from magic
bytes. Duration is read from container metadata (WAV header, Ogg granule position, WebM
block timestamps, MP4 `mvhd`), so over-long clips are rejected before any paid STT call.
If a duration cannot be determined it is None, and the endpoint falls back to the duration
the STT provider reports.
"""

import struct
from dataclasses import dataclass
from typing import Literal

AudioFormat = Literal["webm", "ogg", "wav", "m4a"]

# Declared MIME types accepted per sniffed container (parameters like ";codecs=opus" are
# stripped first). Browsers label MediaRecorder output differently.
ALLOWED_TYPES: dict[AudioFormat, set[str]] = {
    "webm": {"audio/webm", "video/webm"},
    "ogg": {"audio/ogg", "audio/opus", "application/ogg"},
    "wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
    "m4a": {"audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac", "video/mp4"},
}
CANONICAL_TYPE: dict[AudioFormat, str] = {
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
}


@dataclass(frozen=True)
class AudioInfo:
    format: AudioFormat
    duration_ms: int | None


def sniff_format(data: bytes) -> AudioFormat | None:
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if data.startswith(b"OggS"):
        return "ogg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[4:8] == b"ftyp":
        return "m4a"
    return None


def inspect_audio(data: bytes) -> AudioInfo | None:
    """Return the container and duration, or None if the bytes are not a supported format."""
    fmt = sniff_format(data)
    if fmt is None:
        return None
    reader = {"webm": _webm_ms, "ogg": _ogg_ms, "wav": _wav_ms, "m4a": _mp4_ms}[fmt]
    try:
        duration = reader(data)
    except (struct.error, IndexError, ValueError, ZeroDivisionError):
        duration = None
    return AudioInfo(fmt, duration if duration is None or duration >= 0 else None)


# --- WAV ----------------------------------------------------------------------------------------


def _wav_ms(data: bytes) -> int | None:
    pos, byte_rate = 12, 0
    while pos + 8 <= len(data):
        chunk_id, size = data[pos : pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        body = pos + 8
        if chunk_id == b"fmt ":
            byte_rate = struct.unpack_from("<I", data, body + 8)[0]
        elif chunk_id == b"data":
            # Streamed WAVs may declare 0 or 0xFFFFFFFF; trust the bytes actually present.
            available = len(data) - body
            size = available if size == 0 or size > available else size
            return round(size * 1000 / byte_rate) if byte_rate else None
        pos = body + size + (size & 1)
    return None


# --- Ogg (Opus / Vorbis) ----------------------------------------------------------------------


def _ogg_ms(data: bytes) -> int | None:
    rate = 48_000  # Opus granule positions are always 48 kHz
    vorbis = data.find(b"\x01vorbis")
    if vorbis != -1 and data.find(b"OpusHead") == -1:
        rate = struct.unpack_from("<I", data, vorbis + 12)[0]
    last = data.rfind(b"OggS")
    granule = struct.unpack_from("<q", data, last + 6)[0]
    return round(granule * 1000 / rate) if granule > 0 else None


# --- WebM / Matroska ------------------------------------------------------------------------------

_SEGMENT, _INFO, _CLUSTER, _BLOCK_GROUP = 0x18538067, 0x1549A966, 0x1F43B675, 0xA0
_TIMECODE_SCALE, _DURATION, _CLUSTER_TIMECODE = 0x2AD7B1, 0x4489, 0xE7
_SIMPLE_BLOCK, _BLOCK = 0xA3, 0xA1
_MASTERS = {_SEGMENT, _INFO, _CLUSTER, _BLOCK_GROUP}
_MAX_ELEMENTS = 200_000


def _vint(data: bytes, pos: int, keep_marker: bool) -> tuple[int, int, bool]:
    """Read an EBML variable-length integer -> (value, length, all_ones)."""
    first = data[pos]
    length = 1
    while length <= 8 and not first & (0x80 >> (length - 1)):
        length += 1
    if length > 8:
        raise ValueError("invalid EBML vint")
    value = first if keep_marker else first & (0xFF >> length)
    for byte in data[pos + 1 : pos + length]:
        value = (value << 8) | byte
    all_ones = value == (1 << (7 * length)) - 1 and not keep_marker
    return value, length, all_ones


def _webm_ms(data: bytes) -> int | None:
    scale_ns = 1_000_000
    declared: float | None = None
    cluster_tc = 0
    last_tc = -1
    pos = 0
    for _ in range(_MAX_ELEMENTS):
        if pos >= len(data) - 1:
            break
        element, id_len, _ = _vint(data, pos, keep_marker=True)
        size, size_len, unknown = _vint(data, pos + id_len, keep_marker=False)
        body = pos + id_len + size_len
        if element in _MASTERS:
            pos = body  # descend (MediaRecorder writes unknown-size Segment and Cluster)
            continue
        if unknown:
            break
        payload = data[body : body + size]
        if element == _TIMECODE_SCALE:
            scale_ns = int.from_bytes(payload, "big") or scale_ns
        elif element == _DURATION:
            declared = struct.unpack(">f" if size == 4 else ">d", payload)[0]
        elif element == _CLUSTER_TIMECODE:
            cluster_tc = int.from_bytes(payload, "big")
        elif element in (_SIMPLE_BLOCK, _BLOCK) and len(payload) >= 4:
            _, track_len, _ = _vint(payload, 0, keep_marker=False)
            relative = struct.unpack_from(">h", payload, track_len)[0]
            last_tc = max(last_tc, cluster_tc + relative)
        pos = body + size
    if declared and declared > 0:
        return round(declared * scale_ns / 1_000_000)
    return round(last_tc * scale_ns / 1_000_000) if last_tc >= 0 else None


# --- MP4 / M4A ----------------------------------------------------------------------------------


def _mp4_ms(data: bytes) -> int | None:
    at = data.find(b"mvhd")
    if at == -1:
        return None
    version = data[at + 4]
    if version == 1:
        timescale, duration = struct.unpack_from(">IQ", data, at + 8 + 16)
    else:
        timescale, duration = struct.unpack_from(">II", data, at + 8 + 8)
    return round(duration * 1000 / timescale) if timescale else None
