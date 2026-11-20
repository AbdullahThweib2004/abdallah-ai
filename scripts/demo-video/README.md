# Demo video generator

Records the English demo of Abdallah AI from the **live site** and assembles
`~/Videos/abdallah-ai-demo.mp4`: 1920×1080, 30 fps, H.264 (CRF 16) + AAC, about 40 s, made to be
readable on a phone.

```bash
scripts/demo-video/run.sh
```

Needs `ffmpeg`, Google Chrome, `uv`, and `ELEVENLABS_API_KEY` in the repo's `.env` (only for the
visitor's line, generated once). Outputs, recordings and audio live in `out/` (gitignored); the
video is never committed.

## What happens

1. `visitor_voice.py`: the visitor's question ("What has Abdallah built?") in an ElevenLabs stock
   voice that is clearly not the assistant's ("Jessica"), saved once and reused. It becomes a WAV
   for Chrome's fake microphone (0.4 s lead-in for the site's noise calibration).
2. `check_transcript.py`: plays that WAV into the live site with voice replies off and prints
   what the panel shows. It must match the line word for word, because the burned-in caption
   shows the line. Change the line or the speed (`--line`, `--speed`, `--name`) until it does.
3. `record.py`: a fresh headless Chrome (GPU on, autoplay blocked like a first visit) at a
   1280×720 viewport with deviceScaleFactor 1.5. The UI is zoomed, so the transcript text is
   about 23 px in the 1920×1080 frames, and the transcript, robot and card fit with no scroll
   (checked and saved in `events.json`). "Say hi" is clicked at once, so the greeting plays and
   lights up word by word. A scripted pointer moves while it plays (the robot follows it). The
   mic click interrupts the greeting. The fake microphone asks the question through the real
   pipeline (listening → transcription → answer), the spoken answer lights up, and the AI opens
   the projects card. It saves:
   - CDP screencast frames (JPEG q95) with timestamps;
   - the audio element's events and a sampled audio clock;
   - the moment the fake microphone opened;
   - every `/api/v1/voice/speak` response.
4. `build.py`: intro card (1.5 s), the page at a constant 30 fps from the frame timestamps, a
   burned-in caption for the visitor's question (56 px on a solid black box with an amber
   border), and outro card (2.5 s). The audio is one track: the greeting until the barge-in,
   the visitor's line, and each answer sentence, each placed at its real start on the same
   clock. The track is mixed and normalized to −16 LUFS. Pacing:
   - the page starts 1 s before the greeting (it is heard about 2.5 s into the video);
   - other silences longer than 1.5 s are shortened, to 2 s for the "thinking" pause before
     the answer;
   - every cut removes the same time range from video and audio.
   Sync (audio events vs. the sampled clock) and every cut are in
   `out/landscape/build/timeline.json`.

## ElevenLabs characters

- The greeting is a static file, so it costs nothing.
- The visitor line costs its length once (24).
- The answer costs its length the first time it is spoken (about 270). The site then serves
  it from its answer and audio caches, so later takes are free as long as the transcript (and
  so the cache key) stays the same.

Check usage in the Vercel logs: `TTS first byte … chars=` for a new synthesis, `TTS cache hit`
for a cached one. Pass `--limit 1000`, because the CLI shows 100 lines by default.
