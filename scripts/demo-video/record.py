"""Record the demo on the live site: page frames (CDP screencast) + every timing needed to mix
the audio afterwards.

    uv run --with playwright python scripts/demo-video/record.py --size 1280x720 --scale 1.5 --out <dir>

Scene: the robot follows a scripted pointer, "Say hi" plays the greeting (words light up in the
transcript), the visitor asks by voice (Chrome's fake microphone plays out/visitor-mic.wav
through the REAL pipeline: listening → transcription → answer), the spoken answer lights up
and the AI opens a card.

Saved in <dir>: frames/NNNNN.jpg + frames.json (epoch timestamps), events.json (audio element
events, when the fake mic opened, the greeting URL), speak/NN.mp3 + speak.json (each
/api/v1/voice/speak response, in request order = playback order).
"""

import argparse
import base64
import json
import math
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = "https://abdallah-thuieb.vercel.app"
HERE = Path(__file__).resolve().parent

# Logged in the page: when the fake microphone opens (its WAV starts playing then) and every
# play/pause/end of the speaker's <audio> element. A visible pointer for the recording.
INIT = """
(() => {
  window.__demo = { audio: [], micStart: null, clock: [] };
  // Audio clock samples while something plays: (wall time, media time) pairs give each clip's
  // real start on the wall clock (for the audio mix and the A/V sync check).
  setInterval(() => {
    const a = document.querySelector("audio[data-voice=speaker]");
    if (a && !a.paused && a.currentTime > 0.05) window.__demo.clock.push({ t: Date.now(), ct: a.currentTime, src: a.currentSrc });
  }, 200);
  const md = navigator.mediaDevices;
  if (md && md.getUserMedia) {
    const original = md.getUserMedia.bind(md);
    md.getUserMedia = async (c) => { const s = await original(c); window.__demo.micStart = Date.now(); return s; };
  }
  // "emptied": the speaker's stop() pauses then reloads the element, which drops "pause".
  for (const type of ["playing", "pause", "ended", "emptied"]) {
    document.addEventListener(type, (e) => {
      const a = e.target;
      if (a instanceof HTMLAudioElement) window.__demo.audio.push({ type, t: Date.now(), src: a.currentSrc || a.src, ct: a.currentTime });
    }, true);
  }
  addEventListener("DOMContentLoaded", () => {
    const c = document.createElement("div");
    c.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24"><path d="M4 2l7 19 2.6-7.4L21 11z" fill="#f2f0ea" stroke="#0a0b0d" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    c.style.cssText = "position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;transform:translate(-100px,-100px);filter:drop-shadow(0 2px 4px rgba(0,0,0,.5))";
    document.body.appendChild(c);
    addEventListener("mousemove", (e) => { c.style.transform = `translate(${e.clientX - 3}px, ${e.clientY - 2}px)`; }, true);
  });
})();
"""


def audio_of(ndjson: bytes) -> bytes:
    audio = b""
    for line in ndjson.decode("utf-8", "replace").splitlines():
        if line.strip():
            data = json.loads(line)
            if "audio" in data:
                audio += base64.b64decode(data["audio"])
    return audio


def refetch_missing(out: Path) -> None:
    """Playwright sometimes returns no body for a streamed response: fetch that sentence again.
    It belongs to the answer just spoken, which the site caches with its audio, so this is
    served from the cache (no ElevenLabs characters)."""
    spoken = json.loads((out / "speak.json").read_text())
    for index, item in enumerate(spoken):
        path = out / "speak" / f"{index:02d}.mp3"
        if path.is_file() and path.stat().st_size:
            continue
        request = urllib.request.Request(
            SITE + "/api/v1/voice/speak",
            data=json.dumps({"text": item["text"], "language": "en", "timestamps": True}).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            audio = audio_of(response.read())
        path.write_bytes(audio)
        item["bytes"], item["refetched"] = len(audio), True
        print(f"refetched sentence {index}: {len(audio)} bytes")
    (out / "speak.json").write_text(json.dumps(spoken, ensure_ascii=False, indent=1))


def glide(page, start, end, ms, steps=None):
    """Smooth (eased) pointer movement."""
    steps = steps or max(8, ms // 16)
    for i in range(1, steps + 1):
        k = i / steps
        e = 0.5 - 0.5 * math.cos(math.pi * k)
        page.mouse.move(start[0] + (end[0] - start[0]) * e, start[1] + (end[1] - start[1]) * e)
        page.wait_for_timeout(ms / steps)
    return end


def center(locator):
    box = locator.bounding_box()
    return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default="1280x720", help="CSS viewport")
    parser.add_argument("--scale", type=float, default=1.5, help="deviceScaleFactor (frames = size × scale)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--greeting-seconds", type=float, default=9.0)
    parser.add_argument("--refetch-only", action="store_true", help="only re-fetch missing sentence audio")
    args = parser.parse_args()
    if args.refetch_only:
        refetch_missing(args.out)
        return 0
    width, height = (int(v) for v in args.size.split("x"))
    frame_w, frame_h = round(width * args.scale), round(height * args.scale)
    out: Path = args.out
    (out / "frames").mkdir(parents=True, exist_ok=True)
    (out / "speak").mkdir(exist_ok=True)
    wav = HERE / "out" / "visitor-mic.wav"

    frames: list[dict] = []
    speaks: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel="chrome",
            headless=True,
            args=[
                "--ignore-gpu-blocklist", "--enable-gpu",
                "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={wav}",
                # A first visit: sound waits for a gesture, so "Say hi" shows.
                "--autoplay-policy=document-user-activation-required",
                "--hide-scrollbars",
            ],
        )  # fmt: skip
        context = browser.new_context(
            viewport={"width": width, "height": height}, device_scale_factor=args.scale,
            permissions=["microphone"], locale="en-US", color_scheme="dark",
        )  # fmt: skip
        context.add_init_script(INIT)
        page = context.new_page()

        def on_request(request):
            if "/api/v1/voice/speak" in request.url:
                speaks.append({"request": request, "text": json.loads(request.post_data)["text"]})

        def on_finished(request):
            for item in speaks:
                if item.get("request") is request:
                    item["body"] = request.response().body()

        page.on("request", on_request)
        page.on("requestfinished", on_finished)

        page.goto(SITE + "/", wait_until="networkidle")
        page.wait_for_selector('.avatar-stage[data-robot="ready"]', timeout=60_000)
        say_hi = page.locator("button[data-greeting-ignore][aria-label]")
        say_hi.wait_for(timeout=15_000)
        page.wait_for_timeout(1200)

        # Frames with their swap timestamps (epoch seconds).
        cdp = context.new_cdp_session(page)

        def on_frame(params):
            index = len(frames)
            (out / "frames" / f"{index:05d}.jpg").write_bytes(base64.b64decode(params["data"]))
            frames.append({"i": index, "t": params["metadata"].get("timestamp", time.time())})
            cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})

        cdp.on("Page.screencastFrame", on_frame)
        # Layout check at this viewport: nothing may scroll; transcript text size in frame pixels.
        layout = page.evaluate(
            """(scale) => { const word = document.querySelector('section.transcript-panel .tw');
              const box = (s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right)]; };
              return { scroll: [document.scrollingElement.scrollHeight, innerHeight, document.scrollingElement.scrollWidth, innerWidth],
                       transcriptFontPx: parseFloat(getComputedStyle(word).fontSize) * scale,
                       transcriptLineBoxPx: word.getBoundingClientRect().height * scale,
                       transcript: box('section.transcript-panel'), robot: box('.avatar-stage'), composer: box('form[data-greeting-skip]') }; }""",
            args.scale,
        )
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 95, "maxWidth": frame_w, "maxHeight": frame_h, "everyNthFrame": 1})
        page.wait_for_timeout(150)

        # 1. "Say hi" right away: the greeting plays and lights up in the transcript.
        here = (width * 0.62, height * 0.30)
        page.mouse.move(*here)
        here = glide(page, here, center(say_hi), 420)
        say_hi.click()
        clicked_at = time.time()
        # 2. Meanwhile the robot follows a smooth scripted pointer.
        here = glide(page, here, (width * 0.80, height * 0.30), 1100)
        here = glide(page, here, (width * 0.66, height * 0.72), 1100)
        here = glide(page, here, (width * 0.50, height * 0.40), 1000)
        page.wait_for_timeout(max(0, int((args.greeting_seconds - (time.time() - clicked_at)) * 1000)))
        # 3. The visitor asks by voice (barge-in stops the greeting).
        mic = page.locator("button[aria-describedby='voice-status voice-privacy']")
        here = glide(page, here, center(mic), 800)
        page.wait_for_timeout(200)
        mic.click()
        here = glide(page, here, (width * 0.5, height * 0.18), 900)
        # 4. The answer is spoken; wait until it has finished.
        page.wait_for_function("() => performance.getEntriesByName('voice:first-audio').length > 0", timeout=60_000)
        page.wait_for_function(
            "() => { const a = document.querySelector('audio[data-voice=speaker]');"
            " return a && a.paused && !document.querySelector('[data-entry^=\"answer:\"] .tw[data-state=current]'); }",
            timeout=90_000,
        )
        page.wait_for_timeout(600)
        cdp.send("Page.stopScreencast")
        page.wait_for_timeout(300)

        events = page.evaluate("() => window.__demo")
        events["greeting_url"] = SITE + "/audio/greeting-en.mp3"
        events["card_open"] = page.locator("aside[aria-labelledby=card-heading]").count()
        events["layout"] = layout
        events["say_hi_at"] = clicked_at
        # The visitor's question as the panel shows it (the caption must match it).
        events["question_text"] = page.evaluate(
            "() => { const p = document.querySelector('section.transcript-panel li:last-child p.text-xs'); return p ? p.lastChild.textContent : ''; }"
        )
        events["answer_text"] = page.evaluate(
            "() => document.querySelector('section.transcript-panel [data-entry^=\"answer:\"] .sr-only')?.textContent ?? ''"
        )
        browser.close()

    saved = []
    for index, item in enumerate(speaks):
        audio = audio_of(item.get("body") or b"")
        (out / "speak" / f"{index:02d}.mp3").write_bytes(audio)
        saved.append({"text": item["text"], "bytes": len(audio)})
    (out / "speak.json").write_text(json.dumps(saved, ensure_ascii=False, indent=1))
    refetch_missing(out)
    (out / "frames.json").write_text(json.dumps(frames))
    (out / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=1))
    span = frames[-1]["t"] - frames[0]["t"] if frames else 0
    print(f"{len(frames)} frames over {span:.1f} s ({len(frames) / max(span, 1e-9):.1f} fps), "
          f"{len(saved)} spoken sentences ({sum(len(s['text']) for s in saved)} chars requested), "
          f"card open: {events['card_open']}\nlayout: {layout}\nquestion in panel: {events['question_text']!r}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
