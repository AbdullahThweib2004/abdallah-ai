"""What does the site's real voice pipeline write for a fake-microphone WAV? (Chrome fake mic on
the live site, voice replies muted so no answer audio is synthesized.)

    uv run --with playwright python scripts/demo-video/check_transcript.py out/visitor-mic.wav [runs]
"""

import json
import sys

from playwright.sync_api import sync_playwright

SITE = "https://abdallah-thuieb.vercel.app"


def transcribe(wav: str) -> str:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", f"--use-file-for-fake-audio-capture={wav}"])  # fmt: skip
        context = browser.new_context(permissions=["microphone"])
        context.add_cookies([{"name": "voice_replies", "value": "off", "url": SITE + "/"}])
        page = context.new_page()
        texts: list[str] = []
        page.on("response", lambda r: texts.append(r.json().get("text", "")) if "/voice/transcribe" in r.url and r.status == 200 else None)
        page.goto(SITE + "/", wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.locator("button[aria-describedby='voice-status voice-privacy']").click()
        page.wait_for_function("() => document.querySelector('section.transcript-panel [data-entry^=\"answer:\"]') !== null", timeout=30_000)
        question = page.evaluate(
            "() => { const p = document.querySelector('section.transcript-panel li:last-child p.text-xs'); return p ? p.lastChild.textContent : ''; }"
        )
        browser.close()
        return json.dumps({"transcribe": texts[:1], "panel": question}, ensure_ascii=False)


if __name__ == "__main__":
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    for _ in range(runs):
        print(transcribe(sys.argv[1]))
