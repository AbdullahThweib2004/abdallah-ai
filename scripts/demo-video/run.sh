#!/usr/bin/env bash
# Regenerate the demo video from the live site (see README.md). The video goes to ~/Videos;
# recordings and audio stay in scripts/demo-video/out/ (gitignored).
set -euo pipefail
cd "$(dirname "$0")/../.."
PW=(uv run --with playwright python)
OUT=scripts/demo-video/out

# 1. The visitor's spoken question (ElevenLabs, once; reused afterwards).
(cd backend && PYTHONPATH=. uv run python ../scripts/demo-video/visitor_voice.py)

# 2. Check that the site's real pipeline transcribes it word for word (no TTS is used).
"${PW[@]}" scripts/demo-video/check_transcript.py "$OUT/visitor-mic.wav" 2

# 3. Record at a 1280×720 viewport, zoomed 1.5× (frames are 1920×1080), 4. assemble.
mkdir -p "$HOME/Videos"
rm -rf "$OUT/landscape"
"${PW[@]}" scripts/demo-video/record.py --size 1280x720 --scale 1.5 --out "$OUT/landscape"
"${PW[@]}" scripts/demo-video/build.py --rec "$OUT/landscape" --out "$HOME/Videos/abdallah-ai-demo.mp4"
