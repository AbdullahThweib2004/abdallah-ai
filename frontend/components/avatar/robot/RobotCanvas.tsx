"use client";

import { Canvas, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import * as THREE from "three";

import type { AvatarState } from "@/hooks/useConversation";
import type { CardSide } from "@/lib/avatar/motion";

import { Robot } from "./Robot";

type Props = {
  state: AvatarState;
  reducedMotion: boolean;
  card: CardSide | null;
  levels?: () => number[] | null;
  /** First frame drawn: the stage hides the orb. */
  onReady: () => void;
  /** Loading or rendering failed for good: the stage falls back to the orb. */
  onFail: (error: Error) => void;
  /** WebGL context lost (temporary): the stage shows the orb but keeps this canvas mounted. */
  onLost: () => void;
  /** The browser restored the context: the stage recreates the robot on a fresh canvas. */
  onRestored: () => void;
};

/** Resolves when the main thread is idle (or soon), so heavy steps run as separate tasks. */
function nextIdle(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(() => resolve(), { timeout: 1000 });
    else window.setTimeout(resolve, 50);
  });
}

/**
 * A tiny studio for reflections: a dark room with a warm key softbox, a cool fill, an amber
 * rim panel and a top strip. Unlit materials only, so it compiles and renders cheaply.
 */
function studioScene(): THREE.Scene {
  const scene = new THREE.Scene();
  const room = new THREE.Mesh(
    new THREE.BoxGeometry(12, 12, 12),
    new THREE.MeshBasicMaterial({ color: "#121418", side: THREE.BackSide }),
  );
  scene.add(room);
  const panel = (color: string, strength: number, width: number, height: number, position: [number, number, number]) => {
    const material = new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide });
    material.color.multiplyScalar(strength);
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, height), material);
    mesh.position.set(...position);
    mesh.lookAt(0, 0, 0);
    scene.add(mesh);
  };
  panel("#fff1de", 7, 4, 2.6, [3.5, 4, 4.5]); // key, top right front
  panel("#cfd8ff", 2.2, 2.4, 4, [-5, 0.5, 3]); // fill, left
  panel("#f0b35b", 5, 4, 2.2, [-3.5, 1.5, -5]); // amber rim, behind left
  panel("#ffffff", 3, 7, 0.8, [0, 5.8, 0]); // top strip
  return scene;
}

function disposeScene(scene: THREE.Scene) {
  scene.traverse((object) => {
    if (object instanceof THREE.Mesh) {
      object.geometry.dispose();
      (object.material as THREE.Material).dispose();
    }
  });
}

/**
 * Prepares the GPU before the first frame without one long main-thread task: in separate idle
 * slices it builds the studio reflections (a procedural scene through PMREM; nothing
 * downloaded), then compiles every shader with `compileAsync` (parallel compile when
 * the browser supports KHR_parallel_shader_compile). Only then does the frame loop start.
 */
function Warmup({ onDone, onFail }: { onDone: () => void; onFail: (error: Error) => void }) {
  const get = useThree((three) => three.get);
  const callbacks = useRef({ onDone, onFail });
  useEffect(() => {
    callbacks.current = { onDone, onFail };
  });
  useEffect(() => {
    const { gl, scene, camera } = get();
    let cancelled = false;
    let target: THREE.WebGLRenderTarget | null = null;
    (async () => {
      performance.mark("avatar:mounted");
      await nextIdle();
      if (cancelled) return;
      const pmrem = new THREE.PMREMGenerator(gl);
      const studio = studioScene();
      target = pmrem.fromScene(studio, 0, 0.1, 100, { size: 128 });
      disposeScene(studio);
      pmrem.dispose();
      scene.environment = target.texture;
      scene.environmentIntensity = 0.75;
      performance.mark("avatar:environment");
      await nextIdle();
      if (cancelled) return;
      // Parallel compile where available (no main-thread stall); a plain compile otherwise.
      if (gl.extensions.has("KHR_parallel_shader_compile")) await gl.compileAsync(scene, camera);
      else gl.compile(scene, camera);
      performance.mark("avatar:compiled");
      if (!cancelled) callbacks.current.onDone();
    })().catch((error: unknown) => {
      if (!cancelled) callbacks.current.onFail(error instanceof Error ? error : new Error(String(error)));
    });
    return () => {
      cancelled = true;
      scene.environment = null;
      target?.dispose();
    };
  }, [get]);
  return null;
}

/**
 * The lazily loaded 3D stage (three.js + react-three-fiber). After the warm-up it renders only
 * while the tab is visible and the stage is on screen; reduced motion renders one frame per change.
 */
export default function RobotCanvas({ state, reducedMotion, card, levels, onReady, onFail, onLost, onRestored }: Props) {
  const anchor = useRef<HTMLDivElement>(null);
  const pointer = useRef<{ x: number; y: number; at: number; touch: boolean } | null>(null);
  const [onScreen, setOnScreen] = useState(true);
  const [tabVisible, setTabVisible] = useState(true);
  // r3f forces a context loss when it unmounts (during the commit, before passive cleanups);
  // only a loss while mounted is reported, so the flag is cleared in a LAYOUT cleanup.
  const mounted = useRef(true);
  useLayoutEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const element = anchor.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => setOnScreen(entry?.isIntersecting ?? true));
    observer.observe(element);
    const onVisibility = () => setTabVisible(document.visibilityState === "visible");
    onVisibility();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  // The head follows the pointer anywhere on the page (touch: the last tap).
  useEffect(() => {
    if (reducedMotion) return;
    const onPointer = (event: PointerEvent) => {
      const touch = event.pointerType === "touch";
      if (touch && event.type === "pointermove") return; // scrolling/dragging, not a look target
      pointer.current = { x: event.clientX, y: event.clientY, at: performance.now(), touch };
    };
    window.addEventListener("pointermove", onPointer, { passive: true });
    window.addEventListener("pointerdown", onPointer, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [reducedMotion]);

  // Stages, each in its own task: WebGL context → robot meshes → environment + shaders → frames.
  const [meshes, setMeshes] = useState(false);
  const [warm, setWarm] = useState(false);
  const running = warm && onScreen && tabVisible;
  const frameloop = !running ? "never" : reducedMotion ? "demand" : "always";

  return (
    <div ref={anchor} aria-hidden="true" className="absolute inset-0">
      <Canvas
        frameloop={frameloop}
        dpr={[1, 1.75]}
        camera={{ position: [0, 0, 6.4], fov: 30, near: 0.1, far: 30 }}
        gl={{ alpha: true, antialias: true, powerPreference: "default" }}
        style={{ pointerEvents: "none" }}
        onCreated={({ gl }) => {
          performance.mark("avatar:context");
          void nextIdle().then(() => {
            if (mounted.current) setMeshes(true);
          });
          gl.setClearColor(0x000000, 0);
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.05;
          // preventDefault() tells the browser we want the context back (`webglcontextrestored`).
          gl.domElement.addEventListener("webglcontextlost", (event) => {
            event.preventDefault();
            if (mounted.current) onLost();
          });
          gl.domElement.addEventListener("webglcontextrestored", () => {
            if (mounted.current) onRestored();
          });
        }}
      >
        <ambientLight intensity={0.25} />
        <hemisphereLight args={["#d9dce3", "#1a1206", 0.35]} />
        <directionalLight position={[3, 4, 5]} intensity={2.1} color="#fff4e6" />
        <directionalLight position={[-4, 1.5, -3.5]} intensity={2.4} color="#f0b35b" />
        <directionalLight position={[4, -1, -4]} intensity={0.9} color="#9fb7ff" />
        {meshes && (
          <>
            <Robot
              state={state}
              reducedMotion={reducedMotion}
              card={card}
              levels={levels}
              pointer={pointer}
              anchor={anchor}
              onReady={onReady}
            />
            <Warmup onDone={() => setWarm(true)} onFail={onFail} />
          </>
        )}
      </Canvas>
    </div>
  );
}
