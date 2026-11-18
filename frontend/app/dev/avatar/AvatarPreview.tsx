"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AvatarStage } from "@/components/avatar/AvatarStage";
import type { AvatarState } from "@/hooks/useConversation";
import { BAR_COUNT } from "@/lib/voice/levels";

const STATES: AvatarState[] = ["idle", "listening", "thinking", "speaking"];
type Motion = "system" | "reduced" | "full";
type Source = "analyser" | "none";
type Card = "none" | "ltr" | "rtl";

function Choice<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: readonly T[]; onChange: (value: T) => void }) {
  return (
    <fieldset className="space-y-2">
      <legend className="eyebrow text-mist-400">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={value === option}
            onClick={() => onChange(option)}
            className="rounded-full border border-ink-700 px-3 py-1.5 text-sm aria-pressed:border-accent aria-pressed:bg-accent aria-pressed:text-accent-ink"
          >
            {option}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

/** Buttons for every state, a fake audio level and motion toggles, for visual tuning. */
export function AvatarPreview() {
  const [state, setState] = useState<AvatarState>("idle");
  const [level, setLevel] = useState(0.5);
  const [source, setSource] = useState<Source>("analyser");
  const [motion, setMotion] = useState<Motion>("system");
  const [card, setCard] = useState<Card>("none");
  const [orb, setOrb] = useState(false);
  const levelRef = useRef(level);
  useEffect(() => {
    levelRef.current = level;
  }, [level]);

  // A fake AnalyserNode: the slider level with a little per-bar movement, like speech.
  const levels = useCallback((): number[] | null => {
    if (source === "none") return null;
    const t = performance.now() / 1000;
    const base = levelRef.current;
    return Array.from({ length: BAR_COUNT }, (_, i) =>
      Math.min(1, Math.max(0, base * (0.7 + 0.3 * Math.sin(t * 9 + i * 1.7)) * (1 - Math.abs(i - 4) * 0.07))),
    );
  }, [source]);

  return (
    <div className="mx-auto grid h-[calc(100dvh-var(--header-height))] max-w-6xl gap-6 overflow-hidden p-4 lg:grid-cols-[1fr_320px]">
      <div className="avatar-frame grid min-h-0 place-items-center rounded-2xl border border-ink-800">
        <AvatarStage
          key={orb ? "orb" : "robot"}
          state={state}
          label={`Avatar: ${state}`}
          levels={levels}
          cardOpen={card !== "none"}
          rtl={card === "rtl"}
          reducedMotion={motion === "system" ? undefined : motion === "reduced"}
          forceOrb={orb}
        />
      </div>
      <div className="space-y-5 overflow-y-auto">
        <Choice label="State" value={state} options={STATES} onChange={setState} />
        <label className="block space-y-2">
          <span className="eyebrow text-mist-400">Fake audio level: {level.toFixed(2)}</span>
          <input type="range" min={0} max={1} step={0.01} value={level} onChange={(e) => setLevel(Number(e.target.value))} className="w-full accent-[var(--color-accent)]" />
        </label>
        <Choice label="Levels" value={source} options={["analyser", "none"] as const} onChange={setSource} />
        <Choice label="Motion" value={motion} options={["system", "reduced", "full"] as const} onChange={setMotion} />
        <Choice label="Card open" value={card} options={["none", "ltr", "rtl"] as const} onChange={setCard} />
        <Choice label="Renderer" value={orb ? "orb" : "robot"} options={["robot", "orb"] as const} onChange={(value) => setOrb(value === "orb")} />
        <p className="text-xs text-mist-400">
          &ldquo;none&rdquo; levels = browser voice / text-only replies (synthetic rhythm). Card &ldquo;ltr&rdquo; opens on the
          right, &ldquo;rtl&rdquo; on the left (desktop); on mobile widths the head looks down at the sheet.
        </p>
      </div>
    </div>
  );
}
