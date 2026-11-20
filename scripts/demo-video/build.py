"""Assemble the demo video from a recording (record.py): intro card, the page at constant 30 fps,
the visitor caption, outro card, and one audio track mixed on the recording's clock.

    uv run --with playwright python scripts/demo-video/build.py --rec <dir> --out <file.mp4>

Audio placement (all on the page's Date.now() clock, from the first video frame):
- the greeting mp3 from its real start (audio-clock samples) until the visitor's barge-in,
- the visitor WAV from the moment the fake microphone opened (Chrome starts the file then),
- each spoken answer sentence (speak/NN.mp3, in playback order) from its real start.

Pacing: the page starts 1 s before the greeting; other silences longer than 1.5 s (2 s for the
"thinking" pause between the question and the answer) are shortened by cutting the SAME time
range from video and audio, so sync is kept (at most one frame of rounding).
"""

import argparse
import json
import re
import subprocess
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FPS = 30
INTRO_S, OUTRO_S = 1.5, 2.5
MAX_SILENCE_S, MAX_THINKING_S = 1.5, 2.0
W, H = 1920, 1080

CARD = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600;700&family=Geist+Mono&display=block" rel="stylesheet">
<style>
html,body{margin:0;width:1920px;height:1080px;background:#0a0b0d;color:#f2f0ea;font-family:Geist,system-ui,sans-serif}
body{display:grid;place-items:center;background:radial-gradient(60% 50% at 50% 38%,rgba(240,179,91,.16),transparent 70%),#0a0b0d}
.box{text-align:center}
.logo{display:inline-grid;place-items:center;width:104px;height:104px;border-radius:24px;background:#f0b35b;color:#1a1206;font-family:'Geist Mono',monospace;font-weight:600;font-size:48px;margin-bottom:28px}
h1{font-size:120px;font-weight:700;letter-spacing:-.02em;margin:0}
p{font-size:48px;color:#cfccc3;margin:28px 0 0}
.links{font-family:'Geist Mono',monospace;font-size:38px;color:#f0b35b;line-height:1.6;margin-top:30px}
.name{margin-top:28px;font-size:46px;font-weight:600}
</style></head><body><div class="box">{BODY}</div></body></html>"""

# The visitor's spoken question, burned in: >= 40 px text on a solid, high-contrast background.
CAPTION = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@500;700&display=block" rel="stylesheet">
<style>html,body{margin:0;background:transparent;font-family:Geist,system-ui,sans-serif}
.c{display:inline-flex;align-items:center;gap:22px;padding:20px 36px;border-radius:22px;background:#0a0b0d;
border:3px solid #f0b35b;color:#ffffff;font-size:56px;font-weight:500;line-height:1.2}
.who{color:#0a0b0d;background:#f0b35b;font-weight:700;font-size:40px;padding:6px 16px;border-radius:12px}</style></head>
<body><div class="c" id="c"><span class="who">Visitor</span><span>“{BODY}”</span></div></body></html>"""


def render_png(html: str, path: Path, element: bool = False) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": W, "height": H})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(400)
        if element:
            page.locator("#c").screenshot(path=str(path), omit_background=True)
        else:
            page.screenshot(path=str(path))
        browser.close()


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stderr


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout  # fmt: skip
    return float(out)


def silences(path: Path, noise: str = "-45dB", minimum: float = 0.3) -> list[tuple[float, float]]:
    log = run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"silencedetect=noise={noise}:d={minimum}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", log)]
    total = duration(path)
    return [(s, ends[i] if i < len(ends) else total) for i, s in enumerate(starts)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--crf", type=int, default=16)
    args = parser.parse_args()
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

    # --- audio segments on the page timeline: (file, start s, max length s or None) ---------
    plays = [a for a in events["audio"] if a["type"] == "playing"]
    clock = events.get("clock", [])
    sync: list[dict] = []

    def origin(play: dict) -> float:
        """Wall-clock start of a clip: the median of its audio-clock samples (media time
        subtracted), else its "playing" event."""
        event = play["t"] / 1000 - play["ct"]
        samples = sorted(c["t"] / 1000 - c["ct"] for c in clock if c["src"] == play["src"])
        if not samples:
            return event
        median = samples[len(samples) // 2]
        spread = samples[int(len(samples) * 0.9)] - samples[int(len(samples) * 0.1)] if len(samples) > 4 else 0.0
        sync.append({"clip": play["src"][-24:], "samples": len(samples), "event_vs_clock_ms": round((event - median) * 1000),
                     "clock_spread_p10_p90_ms": round(spread * 1000)})  # fmt: skip
        return median

    segments: list[tuple[Path, float, float | None]] = []
    greeting = work / "greeting.mp3"
    if not greeting.is_file():
        urllib.request.urlretrieve(events["greeting_url"], greeting)
    g_play = next(a for a in plays if "greeting" in a["src"])
    g_start = origin(g_play) - t0
    # The mic click stops the greeting (barge-in): the speaker pauses and reloads the element,
    # which fires "emptied" (the queued "pause" is dropped). Fallback: when the mic opened.
    next_play = min((a["t"] for a in plays if a["t"] > g_play["t"]), default=float("inf"))
    stops = [a["t"] for a in events["audio"]
             if a["type"] in ("pause", "ended", "emptied") and g_play["t"] < a["t"] < next_play]  # fmt: skip
    g_stop = (min(stops) if stops else events["micStart"]) / 1000
    segments.append((greeting, g_start, g_stop - t0 - g_start))
    mic = events["micStart"] / 1000 - t0
    segments.append((HERE / "out" / "visitor-mic.wav", mic, None))
    seen: list[str] = []
    for a in plays:
        if "greeting" not in a["src"] and a["src"] not in seen:
            seen.append(a["src"])
    for k, src in enumerate(seen):
        path = rec / "speak" / f"{k:02d}.mp3"
        if path.is_file() and path.stat().st_size:
            segments.append((path, origin(next(a for a in plays if a["src"] == src)) - t0, None))
    answer_start = min(s for _, s, _ in segments[2:])
    speech_end = mic + visitor["lead_s"] + visitor["speech_s"]

    # --- mix the page part (no cards yet) ----------------------------------------------------
    inputs, filters = [], []
    for i, (path, start, length) in enumerate(segments):
        inputs += ["-i", str(path)]
        trim = f"atrim=0:{length:.3f}," if length else ""
        delay = int(round(start * 1000))
        fade = f"afade=t=out:st={max(length - 0.12, 0):.3f}:d=0.12," if length else ""
        filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,{trim}{fade}adelay={delay}|{delay}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(segments)))
    filters.append(f"{mix}amix=inputs={len(segments)}:normalize=0:duration=longest,apad=whole_dur={main_s:.3f},atrim=0:{main_s:.3f}[mix]")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[mix]",
         "-c:a", "pcm_s16le", "-ar", "48000", str(work / "main.wav")])  # fmt: skip

    # --- pacing: shorten long silences (same range cut from video and audio) ----------------
    cuts: list[tuple[float, float]] = []
    for a, b in silences(work / "main.wav"):
        thinking = a < answer_start and b > speech_end
        allowed = MAX_THINKING_S if thinking else MAX_SILENCE_S
        if b - a > allowed + 0.05:
            if b >= main_s - 0.05:  # trailing: keep a short hold before the outro
                cuts.append((a + 0.6, b))
            elif a <= 0.05:  # leading (before the greeting starts)
                cuts.append((0.0, b - 0.25))
            else:
                cuts.append((a + allowed / 2, b - allowed / 2))
    # The greeting voice should start ~1 s into the page (~2.5 s into the video): drop the
    # first moment of footage (the pointer is already gliding to "Say hi"; the click stays in).
    lead = g_start - 1.0
    if lead > 0.05 and not any(a <= 0.05 for a, _ in cuts):
        cuts.insert(0, (0.0, lead))
    cuts = [(round(a * FPS) / FPS, round(b * FPS) / FPS) for a, b in cuts if b - a > 0.05]

    def mapped(t: float) -> float:
        return t - sum(min(b, max(t, a)) - a for a, b in cuts)

    keep = "+".join(f"between(t,{a:.4f},{b:.4f})" for a, b in cuts) or "0"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(work / "main.wav"),
         "-af", f"aselect='not({keep})',asetpts=N/SR/TB", str(work / "main-cut.wav")])  # fmt: skip
    page_s = duration(work / "main-cut.wav")

    # --- cards and caption ------------------------------------------------------------------
    render_png(CARD.replace("{BODY}", '<div class="logo">A</div><h1>Abdallah AI</h1><p>Don’t just visit my portfolio. Talk to it.</p>'), work / "intro.png")
    render_png(CARD.replace("{BODY}", '<div class="logo">A</div><h1>Abdallah AI</h1><div class="links">abdallah-thuieb.vercel.app<br>github.com/AbdullahThweib2004/abdallah-ai</div><div class="name">Abdallah Thuieb</div>'), work / "outro.png")  # noqa: E501
    question = events.get("question_text") or visitor["line"]
    render_png(CAPTION.replace("{BODY}", question), work / "caption.png", element=True)
    cap_on = mapped(mic + visitor["lead_s"] - 0.1)
    cap_off = max(cap_on + 2.5, mapped(answer_start) - 0.2)

    # --- video: page (cut, + caption), cards, concat + audio --------------------------------
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(args.crf), "-pix_fmt", "yuv420p", "-r", str(FPS)]
    page = work / "page.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "frames.txt"),
         "-i", str(work / "caption.png"),
         "-filter_complex",
         f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0a0b0d,fps={FPS},setsar=1,"
         f"select='not({keep})',setpts=N/FRAME_RATE/TB[p];"
         f"[p][1:v]overlay=x=(W-w)/2:y=H-h-150:enable='between(t,{cap_on:.3f},{cap_off:.3f})',"
         f"fade=t=in:st=0:d=0.25,fade=t=out:st={page_s - 0.35:.3f}:d=0.35,format=yuv420p[v]",
         "-map", "[v]", "-t", f"{page_s:.3f}", *enc, str(page)])  # fmt: skip
    for name, seconds in (("intro", INTRO_S), ("outro", OUTRO_S)):
        run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", str(seconds), "-i", str(work / f"{name}.png"),
             "-vf", f"scale={W}:{H},setsar=1,fade=t=in:st=0:d=0.35,fade=t=out:st={seconds - 0.35}:d=0.35,format=yuv420p",
             *enc, str(work / f"{name}.mp4")])  # fmt: skip
    total = INTRO_S + page_s + OUTRO_S
    run(["ffmpeg", "-v", "error", "-y", "-i", str(work / "main-cut.wav"),
         "-af", f"adelay={int(INTRO_S * 1000)}|{int(INTRO_S * 1000)},apad=whole_dur={total:.3f},atrim=0:{total:.3f},"
                "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000",  # social feeds play at about -16 LUFS
         "-ar", "48000", str(work / "audio.wav")])  # fmt: skip
    run(["ffmpeg", "-v", "error", "-y", "-i", str(work / "intro.mp4"), "-i", str(page), "-i", str(work / "outro.mp4"),
         "-i", str(work / "audio.wav"),
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a",
         *enc, "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(args.out)])  # fmt: skip

    timeline = {
        "segments_in_video_s": [(p.name, round(mapped(s) + INTRO_S, 3)) for p, s, _ in segments],
        "greeting_starts_s": round(mapped(g_start) + INTRO_S, 3),
        "caption_s": [round(cap_on + INTRO_S, 3), round(cap_off + INTRO_S, 3)],
        "caption_text": question,
        "cuts_in_page_s": [(round(a, 3), round(b, 3)) for a, b in cuts],
        "sync": sync,
        "duration": round(total, 3),
    }
    (work / "timeline.json").write_text(json.dumps(timeline, indent=1, ensure_ascii=False))
    print(json.dumps(timeline, ensure_ascii=False))
    print(f"{args.out}: {duration(args.out):.2f} s, {args.out.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
