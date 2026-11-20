# Demo video generator

Records the English demo of Abdallah AI from the **live site** and assembles two videos:

- `~/Videos/abdallah-ai-demo.mp4`: 1920×1080, 30 fps, H.264 (CRF 20) + AAC 128 kbps, ≤ 60 s
- `~/Videos/abdallah-ai-demo-portrait.mp4`: 1080×1350 for LinkedIn (recorded at that viewport,
  so the robot, the transcript panel and the card all fit without cropping)

```bash
scripts/demo-video/run.sh
```

Needs `ffmpeg`, Google Chrome, `uv`, and `ELEVENLABS_API_KEY` in the repo's `.env` (only for the
visitor's line, generated once). Outputs, recordings and audio live in `out/` (gitignored); the
videos are never committed.

## What happens

1. `visitor_voice.py`: the visitor's question ("Hi! What has Abdallah built?") in an ElevenLabs
   stock voice that is clearly not the assistant's ("Jessica"), saved once and reused. It becomes
   a WAV for Chrome's fake microphone (1 s lead-in for the site's noise calibration).
2. `record.py`: a fresh headless Chrome (GPU on, autoplay blocked like a first visit) on
   https://abdallah-thuieb.vercel.app. A scripted pointer moves (the robot follows it), "Say hi"
   plays the greeting (words light up in the transcript), the mic click interrupts it and the
   fake microphone asks the question through the real pipeline (listening → transcription →
   answer), the spoken answer lights up and the AI opens the projects card. It saves CDP
   screencast frames with timestamps, the audio element's events and a sampled audio clock,
   the moment the fake microphone opened, and every `/api/v1/voice/speak` response.
3. `build.py`: intro and outro cards (rendered HTML), the page at constant 30 fps from the frame
   timestamps, a burned-in caption for the visitor's question, and one audio track: the greeting
   (until the barge-in), the visitor's line, and each answer sentence, each placed at its real
   start on the same clock (sync error measured in `out/<name>/build/timeline.json`), mixed and
   normalized to −16 LUFS.

## ElevenLabs characters

The greeting is a static file (0). The visitor line costs its length once (28). The answer costs
its length the first time it is spoken (about 380); the site then serves it from its answer and
audio caches, so later takes cost nothing as long as the transcript (and so the cache key) stays
the same. Check usage in the Vercel logs (`TTS first byte … chars=` vs `TTS cache hit`).
