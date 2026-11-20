"""The visitor's spoken question for the demo video (ElevenLabs, a stock voice that is clearly
not the assistant's), plus a WAV for Chrome's fake microphone.

    cd backend && PYTHONPATH=. uv run python ../scripts/demo-video/visitor_voice.py

Runs once: if out/<name>.mp3 exists it is reused (no ElevenLabs characters). The WAV has 0.4 s
of leading silence (the site's recorder calibrates background noise first) and 3 s of trailing
silence (its voice-activity detection ends the turn after 1.1 s of quiet).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import httpx

from app.core.config import get_settings

# Chosen because Whisper (the site's real pipeline) transcribes it word for word; check with
# check_transcript.py after any change.
LINE = "What has Abdallah built?"
# "Jessica": warm, conversational American female stock voice (the assistant is "Chris").
VOICE_ID = "cgSgspJ2msm6clMCkdW9"
MODEL = "eleven_multilingual_v2"
SPEED = 0.9  # a little slower: clearer for speech recognition
LEAD_S = 0.4  # the site's recorder keeps speech heard during its noise calibration
OUT = Path(__file__).resolve().parent / "out"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--line", default=LINE)
    parser.add_argument("--voice", default=VOICE_ID)
    parser.add_argument("--speed", type=float, default=SPEED)
    parser.add_argument("--name", default="visitor", help="output base name in out/")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    mp3, wav, meta = OUT / f"{args.name}.mp3", OUT / f"{args.name}-mic.wav", OUT / f"{args.name}.json"
    used = 0
    if not mp3.is_file():
        key = get_settings().elevenlabs_api_key
        if key is None:
            print("ELEVENLABS_API_KEY is not set", file=sys.stderr)
            return 1
        response = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{args.voice}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": key.get_secret_value(), "Accept": "audio/mpeg"},
            json={
                "text": args.line, "model_id": MODEL, "language_code": "en",
                "voice_settings": {"stability": 0.6, "similarity_boost": 0.75, "speed": args.speed},
            },  # fmt: skip
            timeout=60,
        )
        response.raise_for_status()
        mp3.write_bytes(response.content)
        used = len(args.line)
    # Fake-mic WAV: 48 kHz mono, short lead-in, 3 s tail.
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-t", str(LEAD_S), "-i", "anullsrc=r=48000:cl=mono",
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
    meta.write_text(json.dumps({"line": args.line, "voice": args.voice, "lead_s": LEAD_S, "speech_s": duration}))
    print(f"visitor line: {duration:.2f} s, ElevenLabs characters used now: {used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
