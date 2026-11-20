"""Assemble the demo video from a recording (record.py): intro card, the page at constant 30 fps,
the visitor caption, outro card, and one audio track mixed on the recording's clock.

    uv run --with playwright python scripts/demo-video/build.py --rec <dir> --out <file.mp4> --size 1920x1080

Audio placement (all on the page's Date.now() clock, offset from the first video frame):
- the greeting mp3 from its "playing" event until the visitor's mic barge-in paused it,
- the visitor WAV from the moment the fake microphone opened (Chrome starts the file then),
- each spoken answer sentence (speak/NN.mp3, in playback order) from its "playing" event.
"""

import argparse
import json
import subprocess
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FPS = 30
INTRO_S, OUTRO_S = 2.5, 3.0

CARD = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600;700&family=Geist+Mono&display=block" rel="stylesheet">
<style>
html,body{margin:0;width:%(w)dpx;height:%(h)dpx;background:#0a0b0d;color:#f2f0ea;font-family:Geist,system-ui,sans-serif}
body{display:grid;place-items:center;background:radial-gradient(60%% 50%% at 50%% 38%%,rgba(240,179,91,.16),transparent 70%%),#0a0b0d}
.box{text-align:center;padding:0 8%%}
.logo{display:inline-grid;place-items:center;width:%(logo)dpx;height:%(logo)dpx;border-radius:22%%;background:#f0b35b;color:#1a1206;font-family:'Geist Mono',monospace;font-weight:600;font-size:%(logof)dpx;margin-bottom:%(gap)dpx}
h1{font-size:%(h1)dpx;font-weight:700;letter-spacing:-.02em;margin:0}
p{font-size:%(p)dpx;color:#cfccc3;margin:%(gap)dpx 0 0;line-height:1.35}
.links{font-family:'Geist Mono',monospace;font-size:%(mono)dpx;color:#f0b35b;line-height:1.7;margin-top:%(gap)dpx}
.name{margin-top:%(gap)dpx;font-size:%(p)dpx;color:#f2f0ea;font-weight:600}
</style></head><body><div class="box">%(body)s</div></body></html>"""

CAPTION = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600&display=block" rel="stylesheet">
<style>html,body{margin:0;background:transparent;font-family:Geist,system-ui,sans-serif}
.c{display:inline-flex;align-items:center;gap:%(gap)dpx;padding:%(py)dpx %(px)dpx;border-radius:999px;background:rgba(16,18,22,.92);
border:1.5px solid rgba(240,179,91,.55);color:#f2f0ea;font-size:%(fs)dpx;box-shadow:0 18px 50px -18px rgba(0,0,0,.9)}
.who{color:#f0b35b;font-weight:600}</style></head>
<body><div class="c" id="c"><span class="who">Visitor</span><span>“%(line)s”</span></div></body></html>"""


def render_png(html: str, path: Path, size: tuple[int, int] | None, transparent: bool = False) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": size[0], "height": size[1]} if size else {"width": 1600, "height": 400})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(400)
        if transparent:
            page.locator("#c").screenshot(path=str(path), omit_background=True)
        else:
            page.screenshot(path=str(path))
        browser.close()


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout  # fmt: skip
    return float(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--size", default="1920x1080")
    args = parser.parse_args()
    w, h = (int(v) for v in args.size.split("x"))
    rec: Path = args.rec
    work = rec / "build"
    work.mkdir(exist_ok=True)
    frames = json.loads((rec / "frames.json").read_text())
    events = json.loads((rec / "events.json").read_text())
    visitor = json.loads((HERE / "out" / "visitor.json").read_text())
    t0 = frames[0]["t"]  # seconds, epoch

    # --- the page at constant 30 fps (each frame shown until the next one's timestamp) -------
    lines = []
    for index, frame in enumerate(frames):
        nxt = frames[index + 1]["t"] if index + 1 < len(frames) else frame["t"] + 1 / FPS
        lines.append(f"file '{(rec / 'frames' / f'{frame['i']:05d}.jpg').resolve()}'\nduration {max(nxt - frame['t'], 0.001):.4f}")
    lines.append(f"file '{(rec / 'frames' / f'{frames[-1]['i']:05d}.jpg').resolve()}'")
    (work / "frames.txt").write_text("\n".join(lines))
    main_s = frames[-1]["t"] - t0 + 1 / FPS

    # --- audio segments: (file, start seconds on the main timeline, max length or None) ------
    segments: list[tuple[Path, float, float | None]] = []
    greeting = work / "greeting.mp3"
    if not greeting.is_file():
        urllib.request.urlretrieve(events["greeting_url"], greeting)
    plays = [a for a in events["audio"] if a["type"] == "playing"]
    clock = events.get("clock", [])
    sync: list[dict] = []

    def origin(play: dict) -> float:
        """Wall-clock start of a clip (seconds, epoch): the median of the audio clock samples of
        its src (media time subtracted), else its "playing" event."""
        event = play["t"] / 1000 - play["ct"]
        samples = sorted(c["t"] / 1000 - c["ct"] for c in clock if c["src"] == play["src"])
        if not samples:
            return event
        median = samples[len(samples) // 2]
        spread = samples[int(len(samples) * 0.9)] - samples[int(len(samples) * 0.1)] if len(samples) > 4 else 0.0
        sync.append({"clip": play["src"][-24:], "samples": len(samples), "event_vs_clock_ms": round((event - median) * 1000),
                     "clock_spread_p10_p90_ms": round(spread * 1000)})  # fmt: skip
        return median
    g_play = next(a for a in plays if "greeting" in a["src"])
    g_start = origin(g_play) - t0
    # The visitor's mic click stops the greeting (barge-in): the speaker pauses and reloads the
    # element, which fires "emptied" (the queued "pause" is dropped). Fallback: the moment the
    # fake microphone opened, right after that click.
    next_play = min((a["t"] for a in plays if a["t"] > g_play["t"]), default=float("inf"))
    stops = [a["t"] for a in events["audio"]
             if a["type"] in ("pause", "ended", "emptied") and g_play["t"] < a["t"] < next_play]  # fmt: skip
    g_stop = (min(stops) if stops else events["micStart"]) / 1000
    segments.append((greeting, g_start, (g_stop - t0 - g_start) if g_stop else None))
    mic = events["micStart"] / 1000 - t0
    segments.append((HERE / "out" / "visitor-mic.wav", mic, None))
    seen: list[str] = []
    for a in plays:
        if "greeting" in a["src"] or a["src"] in seen:
            continue
        seen.append(a["src"])
    for k, src in enumerate(seen):
        first = next(a for a in plays if a["src"] == src)
        path = rec / "speak" / f"{k:02d}.mp3"
        if path.is_file() and path.stat().st_size:
            segments.append((path, origin(first) - t0, None))

    # --- mix: intro silence + segments + outro silence ------------------------------------
    inputs, filters = [], []
    for i, (path, start, length) in enumerate(segments):
        inputs += ["-i", str(path)]
        trim = f"atrim=0:{length:.3f}," if length else ""
        delay = int(round((start + INTRO_S) * 1000))
        filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,{trim}afade=t=out:st={max((length or 99) - 0.12, 0):.3f}:d=0.12,adelay={delay}|{delay}[a{i}]")
    total = INTRO_S + main_s + OUTRO_S
    mix = "".join(f"[a{i}]" for i in range(len(segments)))
    filters.append(f"{mix}amix=inputs={len(segments)}:normalize=0:duration=longest,apad=whole_dur={total:.3f},atrim=0:{total:.3f},"
                   # Social feeds play at about -16 LUFS.
                   "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[mix]")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[mix]",
         "-c:a", "pcm_s16le", "-ar", "48000", str(work / "audio.wav")])  # fmt: skip

    # --- cards and caption ----------------------------------------------------------------
    scale = w / 1920 if w >= h else w / 1080
    sizes = {"w": w, "h": h, "logo": int(96 * scale), "logof": int(44 * scale), "gap": int(26 * scale),
             "h1": int(104 * scale), "p": int(40 * scale), "mono": int(30 * scale)}  # fmt: skip
    intro = CARD % {**sizes, "body": '<div class="logo">A</div><h1>Abdallah AI</h1><p>Don’t just visit my portfolio. Talk to it.</p>'}
    outro = CARD % {**sizes, "body": '<div class="logo">A</div><h1>Abdallah AI</h1><div class="links">abdallah-thuieb.vercel.app<br>github.com/AbdullahThweib2004/abdallah-ai</div><div class="name">Abdallah Thuieb</div>'}
    render_png(intro, work / "intro.png", (w, h))
    render_png(outro, work / "outro.png", (w, h))
    cs = 1.0 if w >= h else 0.92
    caption = CAPTION % {"line": visitor["line"], "fs": int(34 * cs), "gap": int(16 * cs), "py": int(16 * cs), "px": int(28 * cs)}
    render_png(caption, work / "caption.png", None, transparent=True)
    # The visitor caption: from the start of the spoken line until the answer starts.
    cap_on = INTRO_S + mic + visitor["lead_s"] - 0.15
    first_answer = min((s for _, s, _ in segments[2:]), default=mic + 6) + INTRO_S
    cap_off = max(cap_on + 2.5, first_answer - 0.3)
    cap_y = f"H-h-{int(h * (0.20 if w >= h else 0.24))}"

    # --- video, in steps with known durations: page (+caption), cards, then concat + audio ---
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS)]
    page = work / "page.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "frames.txt"),
         "-i", str(work / "caption.png"),
         "-filter_complex",
         f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x0a0b0d,fps={FPS},setsar=1[p];"
         f"[p][1:v]overlay=x=(W-w)/2:y={cap_y}:enable='between(t,{cap_on - INTRO_S:.3f},{cap_off - INTRO_S:.3f})',"
         f"fade=t=in:st=0:d=0.35,fade=t=out:st={main_s - 0.45:.3f}:d=0.45,format=yuv420p[v]",
         "-map", "[v]", "-t", f"{main_s:.3f}", *enc, str(page)])  # fmt: skip
    for name, seconds in (("intro", INTRO_S), ("outro", OUTRO_S)):
        run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", str(seconds), "-i", str(work / f"{name}.png"),
             "-vf", f"scale={w}:{h},setsar=1,fade=t=in:st=0:d=0.5,fade=t=out:st={seconds - 0.45}:d=0.45,format=yuv420p",
             *enc, str(work / f"{name}.mp4")])  # fmt: skip
    for name in ("intro", "page", "outro"):
        print(f"  {name}: {duration(work / f'{name}.mp4'):.3f} s")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(work / "intro.mp4"), "-i", str(page), "-i", str(work / "outro.mp4"),
         "-i", str(work / "audio.wav"),
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a",
         *enc, "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(args.out)])  # fmt: skip
    timeline = {"t0": t0, "segments": [(p.name, round(s + INTRO_S, 3), None if l is None else round(l, 3)) for p, s, l in segments],
                "caption": [round(cap_on, 3), round(cap_off, 3)], "duration": round(total, 3), "sync": sync}  # fmt: skip
    (work / "timeline.json").write_text(json.dumps(timeline, indent=1))
    print(json.dumps(timeline))
    print(f"{args.out}: {duration(args.out):.2f} s, {args.out.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
