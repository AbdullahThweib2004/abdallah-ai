import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  MAX_RECOVERY_ATTEMPTS,
  initialRobotStatus,
  mountsRobot,
  robotReducer,
  showsOrb,
  type RobotEvent,
  type RobotStatus,
} from "../lib/avatar/recovery.ts";

const run = (events: RobotEvent[], from: RobotStatus = initialRobotStatus): RobotStatus =>
  events.reduce(robotReducer, from);

const drawing = run([{ type: "start", webgl: true }, { type: "ready" }]);

describe("robot recovery after a WebGL context loss", () => {
  it("shows the orb while lost, keeping the lost canvas mounted for the restore event", () => {
    const lost = robotReducer(drawing, { type: "lost" });
    assert.equal(lost.phase, "lost");
    assert.equal(showsOrb(lost.phase), true);
    assert.equal(mountsRobot(lost.phase), true);
    assert.equal(lost.generation, drawing.generation);
  });

  it("recreates the robot on a fresh canvas when the context is restored", () => {
    const back = run([{ type: "lost" }, { type: "restored" }], drawing);
    assert.equal(back.phase, "loading");
    assert.equal(back.generation, drawing.generation + 1);
    const ready = robotReducer(back, { type: "ready" });
    assert.equal(ready.phase, "ready");
    assert.equal(showsOrb(ready.phase), false);
    assert.equal(ready.attempts, 0);
  });

  it("ignores the late loss of the replaced canvas (force-lost on unmount)", () => {
    const back = run([{ type: "lost", generation: 0 }, { type: "restored", generation: 0 }], drawing);
    assert.equal(back.generation, 1);
    const stale = robotReducer(back, { type: "lost", generation: 0 });
    assert.equal(stale, back);
    assert.equal(robotReducer(stale, { type: "ready", generation: 1 }).phase, "ready");
    assert.equal(robotReducer(back, { type: "lost", generation: 1 }).phase, "lost");
  });

  it("retries on visibility/interaction when no restore event comes, if WebGL works", () => {
    const lost = robotReducer(drawing, { type: "lost" });
    assert.equal(robotReducer(lost, { type: "retry", webgl: false }), lost); // keeps waiting
    const retried = robotReducer(lost, { type: "retry", webgl: true });
    assert.equal(retried.phase, "loading");
    assert.equal(retried.generation, 1);
  });

  it("does not fall back permanently on errors caused by the loss", () => {
    const lost = run([{ type: "lost" }, { type: "error" }], drawing);
    assert.equal(lost.phase, "lost");
  });

  it("gives up after repeated losses before the robot draws again", () => {
    let status = robotReducer(drawing, { type: "lost" });
    for (let attempt = 0; attempt < MAX_RECOVERY_ATTEMPTS; attempt += 1) {
      status = run([{ type: "restored" }, { type: "lost" }], status);
    }
    assert.equal(status.phase, "lost");
    assert.equal(robotReducer(status, { type: "restored" }).phase, "failed");
  });

  it("still falls back for good on real errors and when WebGL is missing", () => {
    assert.equal(robotReducer(drawing, { type: "error" }).phase, "failed");
    assert.equal(run([{ type: "start", webgl: false }]).phase, "failed");
    const failed = run([{ type: "error" }, { type: "restored" }, { type: "retry", webgl: true }], drawing);
    assert.equal(failed.phase, "failed");
    assert.equal(mountsRobot(failed.phase), false);
  });

  it("ignores stray events in other phases", () => {
    assert.equal(robotReducer(initialRobotStatus, { type: "restored" }), initialRobotStatus);
    assert.equal(robotReducer(drawing, { type: "retry", webgl: true }), drawing);
    assert.equal(robotReducer(drawing, { type: "start", webgl: true }), drawing);
  });
});
