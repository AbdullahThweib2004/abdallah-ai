"use client";

import dynamic from "next/dynamic";
import { Component, type ReactNode, useCallback, useEffect, useReducer, useRef, useSyncExternalStore } from "react";

import type { AvatarState } from "@/hooks/useConversation";
import { type CardSide, cardSideFor } from "@/lib/avatar/motion";
import { initialRobotStatus, mountsRobot, robotReducer, showsOrb } from "@/lib/avatar/recovery";
import { isSoftwareRenderer } from "@/lib/avatar/renderer";

const WAVE_BARS = [0.45, 0.8, 0.6, 1, 0.7, 0.9, 0.5, 0.75, 0.4];

// three.js + react-three-fiber live in their own chunk, fetched only after first paint.
const RobotCanvas = dynamic(() => import("./robot/RobotCanvas"), { ssr: false });

type Props = {
  state: AvatarState;
  label: string;
  /**
   * Live per-bar audio levels (0..1): the microphone while listening, the playing answer
   * while speaking. Null (or absent) means nothing measurable plays (e.g. the browser voice).
   */
  levels?: () => number[] | null;
  /** A card is open (side panel on desktop, bottom sheet on mobile): the head turns toward it. */
  cardOpen?: boolean;
  rtl?: boolean;
  /** Overrides `prefers-reduced-motion` (the dev preview's toggle). */
  reducedMotion?: boolean;
  /** Dev preview only: never load the robot, show the orb. */
  forceOrb?: boolean;
};

function useMedia(query: string, serverValue: boolean): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const media = window.matchMedia(query);
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => serverValue,
  );
}

/** WebGL with GPU acceleration (software rendering counts as unavailable). */
function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    if (!context) return false;
    // Software WebGL (no GPU) would block the main thread for seconds: show the orb instead.
    const info = context.getExtension("WEBGL_debug_renderer_info");
    const renderer = info ? context.getParameter(info.UNMASKED_RENDERER_WEBGL) : context.getParameter(context.RENDERER);
    context.getExtension("WEBGL_lose_context")?.loseContext();
    return !isSoftwareRenderer(typeof renderer === "string" ? renderer : null);
  } catch {
    return false;
  }
}

/** Any error while loading or rendering the robot switches the stage back to the orb. */
class RobotBoundary extends Component<{ onError: (error: Error) => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error) {
    this.props.onError(error);
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

/**
 * The avatar is the hero. It sizes itself from its container (`cqmin`), so place it inside
 * an element with `container-type: size`. The 3D robot loads lazily after first paint; until
 * it draws its first frame (or if WebGL is missing or anything fails) the CSS orb shows in the
 * same box, so nothing shifts. Visual states of the orb come from `data-state` in CSS.
 */
export function AvatarStage({ state, label, levels, cardOpen = false, rtl = false, reducedMotion, forceOrb = false }: Props) {
  const stageRef = useRef<HTMLDivElement>(null);
  const barRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const [{ phase: robot, generation }, dispatch] = useReducer(robotReducer, initialRobotStatus);
  const prefersReduced = useMedia("(prefers-reduced-motion: reduce)", false);
  const desktop = useMedia("(min-width: 64rem)", true);
  const still = reducedMotion ?? prefersReduced;
  const card: CardSide | null = cardOpen ? cardSideFor(desktop, rtl) : null;
  const showOrb = showsOrb(robot);

  // Mount the robot after the page has painted and the main thread is idle. Only once: when
  // the route is kept in a hidden <Activity> and shown again, effects re-run but state survives.
  const started = useRef(false);
  useEffect(() => {
    if (forceOrb || started.current) return;
    let cancelled = false;
    let idle = 0;
    const start = () => {
      if (cancelled) return;
      started.current = true;
      performance.mark("avatar:start");
      dispatch({ type: "start", webgl: webglAvailable() });
    };
    const schedule = () => {
      if (typeof window.requestIdleCallback === "function") idle = window.requestIdleCallback(start, { timeout: 2500 });
      else idle = window.setTimeout(start, 600);
    };
    if (document.readyState === "complete") schedule();
    else window.addEventListener("load", schedule, { once: true });
    return () => {
      cancelled = true;
      window.removeEventListener("load", schedule);
      if (typeof window.cancelIdleCallback === "function") window.cancelIdleCallback(idle);
      window.clearTimeout(idle);
    };
  }, [forceOrb]);

  // Orb mode: drive its bars and input ring from real audio, one frame at a time, without
  // React re-renders. Skipped under reduced motion and once the robot is drawing.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || !showOrb || !levels || (state !== "listening" && state !== "speaking")) return;
    if (still) return;
    let frame = 0;
    const draw = () => {
      const values = levels();
      stage.dataset.live = values ? "true" : "false";
      if (values) {
        const average = values.reduce((sum, value) => sum + value, 0) / values.length;
        stage.style.setProperty("--level", average.toFixed(3));
        values.forEach((value, index) => {
          barRefs.current[index]?.style.setProperty("--bar", (0.18 + value * 0.82).toFixed(3));
        });
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      stage.dataset.live = "false";
      stage.style.removeProperty("--level");
    };
  }, [state, levels, showOrb, still]);

  // WebGL context lost: the orb shows meanwhile. Recreate the robot when the browser restores
  // the context (onRestored), or on the next visibility change / interaction if it never does.
  useEffect(() => {
    if (robot !== "lost") return;
    const retry = () => dispatch({ type: "retry", webgl: webglAvailable() });
    const onVisibility = () => {
      if (document.visibilityState === "visible") retry();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pointerdown", retry, { passive: true });
    window.addEventListener("keydown", retry);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointerdown", retry);
      window.removeEventListener("keydown", retry);
    };
  }, [robot]);

  // Callbacks are bound to the canvas generation they were created for (see recovery.ts).
  const fail = useCallback(
    (error: Error) => {
      console.warn("Avatar: 3D robot unavailable, showing the orb.", error.message);
      dispatch({ type: "error", generation });
    },
    [generation],
  );
  const lost = useCallback(() => {
    console.info("Avatar: WebGL context lost, showing the orb until it is restored.");
    dispatch({ type: "lost", generation });
  }, [generation]);
  const restored = useCallback(() => dispatch({ type: "restored", generation }), [generation]);
  const ready = useCallback(() => dispatch({ type: "ready", generation }), [generation]);

  return (
    <div
      ref={stageRef}
      className="avatar-stage relative aspect-square"
      data-state={state}
      data-robot={robot}
      role="img"
      aria-label={label}
    >
      <div aria-hidden="true" className="avatar-glow absolute -inset-[14%] rounded-full" />

      <div aria-hidden="true" className="avatar-orb-layer absolute inset-0">
        <div className="avatar-ring absolute -inset-[7%] rounded-full border border-ink-700" />
        <div className="avatar-ring-level absolute -inset-[7%] rounded-full border-2 border-accent" />
        <div className="avatar-ring-thinking absolute -inset-[3.5%] rounded-full border-2 border-dashed border-accent/60" />
        <div className="avatar-media absolute inset-0 overflow-hidden rounded-full border border-accent/25 bg-ink-900">
          <div className="avatar-orb absolute inset-0" />
        </div>
        <div className="absolute inset-x-0 top-1/2 flex h-[20%] -translate-y-1/2 items-center justify-center">
          <div className="flex h-full items-center gap-1.5">
            {WAVE_BARS.map((height, index) => (
              <span
                key={index}
                ref={(element) => {
                  barRefs.current[index] = element;
                }}
                className="avatar-wave-bar block w-1 rounded-full bg-accent sm:w-1.5"
                style={{ height: `${height * 100}%`, ["--wave-delay" as string]: `${index * 110}ms` }}
              />
            ))}
          </div>
        </div>
      </div>

      {mountsRobot(robot) && (
        <div key={generation} className="avatar-robot absolute -inset-[16%]">
          <RobotBoundary onError={fail}>
            <RobotCanvas
              state={state}
              reducedMotion={still}
              card={card}
              levels={levels}
              onReady={ready}
              onFail={fail}
              onLost={lost}
              onRestored={restored}
            />
          </RobotBoundary>
        </div>
      )}
    </div>
  );
}
