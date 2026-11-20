#!/usr/bin/env bash
# Regenerate the demo videos from the live site (see README.md). Outputs go to ~/Videos;
# recordings and audio stay in scripts/demo-video/out/ (gitignored).
set -euo pipefail
cd "$(dirname "$0")/../.."
PW=(uv run --with playwright python)

# 1. The visitor's spoken question (ElevenLabs, once; reused afterwards).
(cd backend && PYTHONPATH=. uv run python ../scripts/demo-video/visitor_voice.py)

# 2. Record both framings on the live site, 3. assemble the videos.
mkdir -p "$HOME/Videos"
for spec in "landscape 1920x1080 abdallah-ai-demo" "portrait 1080x1350 abdallah-ai-demo-portrait"; do
  read -r name size file <<<"$spec"
  rm -rf "scripts/demo-video/out/$name"
  "${PW[@]}" scripts/demo-video/record.py --size "$size" --out "scripts/demo-video/out/$name"
  "${PW[@]}" scripts/demo-video/build.py --rec "scripts/demo-video/out/$name" --out "$HOME/Videos/$file.mp4" --size "$size"
done
