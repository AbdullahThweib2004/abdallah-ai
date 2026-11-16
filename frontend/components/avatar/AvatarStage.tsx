import Image from "next/image";

import type { AvatarState } from "@/hooks/useConversation";

const WAVE_BARS = [0.45, 0.8, 0.6, 1, 0.7, 0.9, 0.5, 0.75, 0.4];

type Props = {
  state: AvatarState;
  /** `/avatar/abdallah.jpg` when the file exists, otherwise null (orb fallback). */
  portraitSrc: string | null;
  label: string;
};

/**
 * The avatar is the hero. It sizes itself from its container (`cqmin`), so place it inside
 * an element with `container-type: size`. Visual states come from `data-state` in CSS.
 *
 * Step 9 swaps the portrait for a lip-synced <video> inside `.avatar-media`; nothing else in
 * the layout depends on what that slot contains.
 */
export function AvatarStage({ state, portraitSrc, label }: Props) {
  return (
    <div className="avatar-stage relative aspect-square" data-state={state} role="img" aria-label={label}>
      <div aria-hidden="true" className="avatar-glow absolute -inset-[14%] rounded-full" />
      <div aria-hidden="true" className="avatar-ring absolute -inset-[7%] rounded-full border border-ink-700" />
      <div aria-hidden="true" className="avatar-ring-thinking absolute -inset-[3.5%] rounded-full border-2 border-dashed border-accent/60" />

      <div className="avatar-media absolute inset-0 overflow-hidden rounded-full border border-accent/25 bg-ink-900">
        {portraitSrc ? (
          <Image src={portraitSrc} alt="" fill priority sizes="(max-width: 768px) 70vw, 420px" className="object-cover" />
        ) : (
          <div aria-hidden="true" className="avatar-orb absolute inset-0" />
        )}
      </div>

      <div
        aria-hidden="true"
        className={`absolute inset-x-0 flex items-center justify-center ${
          portraitSrc ? "bottom-[-4%] h-[10%]" : "top-1/2 h-[20%] -translate-y-1/2"
        }`}
      >
        <div className={`flex h-full items-center gap-1.5 ${portraitSrc ? "rounded-full bg-ink-950/80 px-3" : ""}`}>
          {WAVE_BARS.map((height, index) => (
            <span
              key={index}
              className="avatar-wave-bar block w-1 rounded-full bg-accent sm:w-1.5"
              style={{ height: `${height * 100}%`, ["--wave-delay" as string]: `${index * 110}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
