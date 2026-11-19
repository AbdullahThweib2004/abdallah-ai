/**
 * Robot lifecycle on the avatar stage, including recovery from a lost WebGL context.
 *
 * Browsers drop WebGL contexts at will (GPU reset, too many contexts, sleep, a backgrounded tab).
 * A loss is temporary: the orb shows while the robot is "lost", and the robot is recreated
 * (a fresh canvas, `generation` + 1) when the context is restored, or on the next visibility
 * change / user interaction if the browser never sends `webglcontextrestored`. Real errors
 * (shader compile, loading) still fall back to the orb for good.
 */

/** "orb": not started; "loading": fetching/compiling; "lost": WebGL context lost, orb shown. */
export type RobotPhase = "orb" | "loading" | "ready" | "lost" | "failed";

/**
 * Events from a robot canvas carry its `generation`: when a canvas is replaced, the old one is
 * force-lost on unmount and its late `webglcontextlost` must not send the new robot back to "lost".
 */
type FromCanvas = { generation?: number };

export type RobotEvent =
  | { type: "start"; webgl: boolean }
  | ({ type: "ready" } & FromCanvas)
  | ({ type: "lost" } & FromCanvas)
  /** `webglcontextrestored` on the lost canvas. */
  | ({ type: "restored" } & FromCanvas)
  /** Tab visible again or the visitor interacted: try a fresh canvas if WebGL works. */
  | { type: "retry"; webgl: boolean }
  | ({ type: "error" } & FromCanvas);

export type RobotStatus = {
  phase: RobotPhase;
  /** Key of the robot canvas: a new value mounts a fresh canvas (and WebGL context). */
  generation: number;
  /** Recreations since the robot last drew a frame: caps a lose → recreate loop. */
  attempts: number;
};

export const MAX_RECOVERY_ATTEMPTS = 3;

export const initialRobotStatus: RobotStatus = { phase: "orb", generation: 0, attempts: 0 };

export function robotReducer(status: RobotStatus, event: RobotEvent): RobotStatus {
  if ("generation" in event && event.generation !== undefined && event.generation !== status.generation) {
    return status; // from a replaced canvas
  }
  switch (event.type) {
    case "start":
      if (status.phase !== "orb") return status;
      return { ...status, phase: event.webgl ? "loading" : "failed" };
    case "ready":
      return status.phase === "loading" ? { ...status, phase: "ready", attempts: 0 } : status;
    case "lost":
      return status.phase === "loading" || status.phase === "ready" ? { ...status, phase: "lost" } : status;
    case "restored":
    case "retry": {
      if (status.phase !== "lost") return status;
      if (event.type === "retry" && !event.webgl) return status; // keep waiting for the next chance
      if (status.attempts >= MAX_RECOVERY_ATTEMPTS) return { ...status, phase: "failed" };
      return { phase: "loading", generation: status.generation + 1, attempts: status.attempts + 1 };
    }
    case "error":
      // While lost, errors are side effects of the loss (e.g. a shader compile on a dead
      // context): keep waiting for the restore instead of giving up.
      return status.phase === "failed" || status.phase === "lost" ? status : { ...status, phase: "failed" };
  }
}

/** The orb shows whenever the robot is not drawing. */
export const showsOrb = (phase: RobotPhase): boolean => phase !== "ready";

/** The robot canvas stays mounted while lost, so the browser can deliver `webglcontextrestored`. */
export const mountsRobot = (phase: RobotPhase): boolean =>
  phase === "loading" || phase === "ready" || phase === "lost";
