"""The visitor's spoken question for the demo video (ElevenLabs, a stock voice that is clearly
not the assistant's), plus a WAV for Chrome's fake microphone.

    cd backend && PYTHONPATH=. uv run python ../scripts/demo-video/visitor_voice.py

Runs once: if out/visitor.mp3 exists it is reused (no ElevenLabs characters). The WAV has 1 s
of leading silence (the site's recorder calibrates background noise first) and 3 s of trailing
silence (its voice-activity detection ends the turn after 1.1 s of quiet).
"""

import json
import subprocess
import sys
from pathlib import Path

import httpx

from app.core.config import get_settings

LINE = "Hi! What has Abdallah built?"
# "Jessica": warm, conversational American female stock voice (the assistant is "Chris").
VOICE_ID = "cgSgspJ2msm6clMCkdW9"
MODEL = "eleven_multilingual_v2"
OUT = Path(__file__).resolve().parent / "out"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    mp3, wav, meta = OUT / "visitor.mp3", OUT / "visitor-mic.wav", OUT / "visitor.json"
    used = 0
    if not mp3.is_file():
        key = get_settings().elevenlabs_api_key
        if key is None:
            print("ELEVENLABS_API_KEY is not set", file=sys.stderr)
            return 1
        response = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": key.get_secret_value(), "Accept": "audio/mpeg"},
            json={"text": LINE, "model_id": MODEL, "language_code": "en"},
            timeout=60,
        )
        response.raise_for_status()
        mp3.write_bytes(response.content)
        used = len(LINE)
    # Fake-mic WAV: 48 kHz mono, 1 s lead-in, 3 s tail.
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-t", "1", "-i", "anullsrc=r=48000:cl=mono",
         "-i", str(mp3), "-f", "lavfi", "-t", "3", "-i", "anullsrc=r=48000:cl=mono",
         "-filter_complex", "[1:a]aresample=48000,aformat=channel_layouts=mono[v];[0:a][v][2:a]concat=n=3:v=0:a=1",
         "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )  # fmt: skip
    duration = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
            capture_output=True, text=True, check=True,
        ).stdout
    )  # fmt: skip
    meta.write_text(json.dumps({"line": LINE, "voice": VOICE_ID, "lead_s": 1.0, "speech_s": duration}))
    print(f"visitor line: {duration:.2f} s, ElevenLabs characters used now: {used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
