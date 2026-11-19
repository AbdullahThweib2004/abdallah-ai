import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { isSoftwareRenderer } from "../lib/avatar/renderer.ts";

describe("software WebGL renderers get the orb", () => {
  it("detects CPU rasterizers", () => {
    for (const name of [
      "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
      "llvmpipe (LLVM 17.0.6, 256 bits)",
      "Microsoft Basic Render Driver",
      "Google SwiftShader",
    ]) {
      assert.equal(isSoftwareRenderer(name), true, name);
    }
  });

  it("keeps the robot on real GPUs and when the renderer is hidden", () => {
    for (const name of [
      "ANGLE (Intel, Mesa Intel(R) Xe Graphics (TGL GT2), OpenGL 4.6)",
      "Apple M2",
      "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
      "Adreno (TM) 650",
      "",
      null,
    ]) {
      assert.equal(isSoftwareRenderer(name), false, String(name));
    }
  });
});
