"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, type RefObject } from "react";
import * as THREE from "three";

import type { AvatarState } from "@/hooks/useConversation";
import {
  CARD_FOCUS_MS,
  average,
  blinkAmount,
  chooseLook,
  damp,
  nextBlinkDelay,
  syntheticLevels,
  type CardSide,
} from "@/lib/avatar/motion";

/** Palette (matches `--color-accent*` / `--color-info` in globals.css). */
const AMBER = new THREE.Color("#f0b35b");
const AMBER_STRONG = new THREE.Color("#ffc977");
const INFO = new THREE.Color("#9fb7ff");

/** Head shape: a slightly flattened, deep ellipsoid. */
const HEAD_SCALE = new THREE.Vector3(1, 0.86, 0.92);
const MOUTH_BARS = 7;

export type RobotInputs = {
  state: AvatarState;
  reducedMotion: boolean;
  card: CardSide | null;
  /** Live audio levels (0..1), or null when nothing measurable plays. */
  levels?: () => number[] | null;
  /** Last pointer position on the page (client px), shared with the canvas. */
  pointer: RefObject<{ x: number; y: number; at: number; touch: boolean } | null>;
  /** The element the head is centered in (for pointer angles). */
  anchor: RefObject<HTMLElement | null>;
};

/** A point on the head surface at (yaw, pitch) radians, pushed out by `lift`. */
function onHead(yaw: number, pitch: number, lift = 1.012): THREE.Vector3 {
  return new THREE.Vector3(
    Math.sin(yaw) * Math.cos(pitch) * HEAD_SCALE.x * lift,
    Math.sin(pitch) * HEAD_SCALE.y * lift,
    Math.cos(yaw) * Math.cos(pitch) * HEAD_SCALE.z * lift,
  );
}

/** A soft round glow drawn in code (no image files). */
function glowTexture(): THREE.CanvasTexture {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const context = canvas.getContext("2d");
  if (context) {
    const gradient = context.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    gradient.addColorStop(0, "rgba(255,255,255,1)");
    gradient.addColorStop(0.35, "rgba(255,255,255,0.35)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, size, size);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** Every geometry, material and texture the robot uses, created once and disposed on unmount. */
function useAssets() {
  const assets = useMemo(() => {
    const glow = glowTexture();
    const emissive = (color: THREE.Color) =>
      new THREE.MeshBasicMaterial({ color: color.clone(), toneMapped: false, transparent: true });
    const additive = (color: THREE.Color, opacity: number) =>
      new THREE.MeshBasicMaterial({
        color: color.clone(),
        toneMapped: false,
        transparent: true,
        opacity,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
    const sprite = (color: THREE.Color, opacity: number) =>
      new THREE.SpriteMaterial({
        map: glow,
        color: color.clone(),
        transparent: true,
        opacity,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      });

    // Visor: the front of a slightly larger ellipsoid (phi = π/2 faces +z in SphereGeometry).
    const visorPhi = 1.62;
    const visorTheta = 1.0;
    const geometries = {
      head: new THREE.SphereGeometry(1, 64, 48),
      visor: new THREE.SphereGeometry(1.012, 64, 32, Math.PI / 2 - visorPhi / 2, visorPhi, Math.PI / 2 - 0.5, visorTheta),
      scan: new THREE.SphereGeometry(1.016, 48, 2, Math.PI / 2 - visorPhi / 2 + 0.06, visorPhi - 0.12, Math.PI / 2 - 0.012, 0.024),
      eye: new THREE.CapsuleGeometry(0.068, 0.11, 6, 16),
      mouthBar: new THREE.CapsuleGeometry(0.024, 0.14, 4, 8),
      earPod: new THREE.CylinderGeometry(0.24, 0.26, 0.16, 48),
      earRing: new THREE.TorusGeometry(0.16, 0.016, 12, 48),
      antennaRod: new THREE.CylinderGeometry(0.014, 0.022, 0.42, 12),
      antennaBase: new THREE.CylinderGeometry(0.06, 0.08, 0.06, 24),
      antennaTip: new THREE.SphereGeometry(0.052, 24, 16),
      neck: new THREE.CylinderGeometry(0.24, 0.32, 0.6, 40),
      neckRing: new THREE.TorusGeometry(0.31, 0.014, 8, 48),
      shoulders: new THREE.SphereGeometry(1, 64, 32, 0, Math.PI * 2, 0, Math.PI / 2),
      chestLight: new THREE.CapsuleGeometry(0.022, 0.16, 4, 12),
      halo: new THREE.TorusGeometry(1.42, 0.006, 6, 160),
    };
    const materials = {
      shell: new THREE.MeshPhysicalMaterial({
        color: "#2b3038",
        metalness: 0.55,
        roughness: 0.36,
        clearcoat: 0.7,
        clearcoatRoughness: 0.22,
      }),
      trim: new THREE.MeshStandardMaterial({ color: "#16191e", metalness: 0.6, roughness: 0.45 }),
      visor: new THREE.MeshPhysicalMaterial({
        color: "#040507",
        metalness: 0.3,
        roughness: 0.06,
        clearcoat: 1,
        clearcoatRoughness: 0.04,
        envMapIntensity: 0.55,
      }),
      rim: emissive(AMBER),
      eyes: emissive(AMBER_STRONG),
      mouth: emissive(AMBER),
      ears: emissive(AMBER),
      tip: emissive(AMBER_STRONG),
      chest: emissive(AMBER),
      scan: additive(AMBER, 0),
      halo: additive(AMBER, 0.12),
      eyeGlow: sprite(AMBER, 0.45),
      tipGlow: sprite(AMBER, 0.5),
      earGlow: sprite(AMBER, 0),
    };
    return { geometries, materials, glow };
  }, []);

  useEffect(
    () => () => {
      Object.values(assets.geometries).forEach((geometry) => geometry.dispose());
      Object.values(assets.materials).forEach((material) => material.dispose());
      assets.glow.dispose();
    },
    [assets],
  );
  return assets;
}

/**
 * An original, stylized robot head: graphite shell, glossy black visor with LED eyes and an
 * equalizer mouth, ear pods with amber rings, a short antenna, neck and shoulders.
 * All motion happens in `useFrame` on refs (no React re-renders per frame).
 */
export function Robot(props: RobotInputs & { onReady: () => void }) {
  const { onReady } = props;
  const { geometries: g, materials } = useAssets();
  // Materials are animated per frame (colors, opacity); `m` in JSX, `mats` in the frame loop.
  const m = materials;
  const mats = useRef(materials);
  const invalidate = useThree((three) => three.invalidate);

  const rig = useRef<THREE.Group>(null);
  const head = useRef<THREE.Group>(null);
  const eyes = useRef<THREE.Group>(null);
  const eyeMeshes = useRef<(THREE.Mesh | null)[]>([]);
  const mouth = useRef<(THREE.Mesh | null)[]>([]);
  const scan = useRef<THREE.Mesh>(null);
  const halo = useRef<THREE.Mesh>(null);
  const shoulders = useRef<THREE.Group>(null);
  const ready = useRef(false);

  // Mutable animation state, kept across frames.
  const sim = useRef({
    yaw: 0,
    pitch: 0,
    roll: 0,
    amp: 0,
    ampSlow: 0,
    listen: 0,
    think: 0,
    speak: 0,
    eyeX: 0,
    eyeY: 0,
    blinkAt: -1,
    nextBlink: 0,
    card: null as CardSide | null,
    cardFocusUntil: 0,
    bars: new Array<number>(MOUTH_BARS).fill(0),
  });

  // The frame loop reads the latest props from a ref. Reduced motion renders on demand:
  // draw a new frame whenever an input changes.
  const inputs = useRef<RobotInputs>(props);
  useEffect(() => {
    inputs.current = props;
    invalidate();
  });

  useFrame(({ clock }, delta) => {
    const now = performance.now();
    const t = clock.elapsedTime;
    const { state, reducedMotion: still, card, levels, pointer, anchor } = inputs.current;
    const s = sim.current;
    const m = mats.current;
    // Snap instantly when motion is reduced (one frame per change); clamp gaps after a pause.
    const dt = still ? 10 : Math.min(delta, 0.1);

    if (card !== s.card) {
      s.cardFocusUntil = card ? now + CARD_FOCUS_MS : 0;
      s.card = card;
    }

    // ----- audio level
    let bars: number[] | null = null;
    if (!still && (state === "listening" || state === "speaking")) bars = levels?.() ?? null;
    const live = bars !== null;
    if (!still && state === "speaking" && !bars) bars = syntheticLevels(t, 9);
    // What drives the mouth/rings, for tests and debugging (DOM write only on change).
    const source = live ? "live" : bars ? "synthetic" : "none";
    if (anchor.current && anchor.current.dataset.audio !== source) anchor.current.dataset.audio = source;
    const level = bars ? average(bars) : 0;
    s.amp = damp(s.amp, level, 20, dt);
    s.ampSlow = damp(s.ampSlow, level, 2.5, dt);
    s.listen = damp(s.listen, state === "listening" ? 1 : 0, 6, dt);
    s.think = damp(s.think, state === "thinking" ? 1 : 0, 5, dt);
    s.speak = damp(s.speak, state === "speaking" ? 1 : 0, 8, dt);

    // ----- where to look
    let yaw = 0;
    let pitch = 0;
    let roll = 0;
    if (!still) {
      const rect = anchor.current?.getBoundingClientRect();
      const center = rect
        ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
        : { x: window.innerWidth / 2, y: window.innerHeight / 2 };
      const look = chooseLook({
        now,
        t,
        pointer: pointer.current,
        center,
        viewport: { width: window.innerWidth, height: window.innerHeight },
        card,
        cardFocusUntil: s.cardFocusUntil,
      }).look;
      yaw = look.yaw;
      pitch = look.pitch;
      // State flavor on top of the look direction.
      roll = s.listen * 0.14; // curious tilt while listening
      pitch -= s.think * 0.1; // looks up a little while thinking
      // Nods: a slow lean with loudness plus a quick dip on syllable onsets.
      pitch += s.speak * (s.ampSlow * 0.08 + Math.max(0, s.amp - s.ampSlow) * 0.35);
    }
    s.yaw = damp(s.yaw, yaw, 4.5, dt);
    s.pitch = damp(s.pitch, pitch, 4.5, dt);
    s.roll = damp(s.roll, roll, 3, dt);
    if (head.current) head.current.rotation.set(s.pitch, s.yaw, s.roll, "YXZ");

    // ----- idle float and breathing
    if (rig.current) rig.current.position.y = still ? 0 : Math.sin(t * 1.15) * 0.035;
    if (shoulders.current) {
      const breath = still ? 1 : 1 + Math.sin(t * 1.15 - 0.6) * 0.012;
      shoulders.current.scale.set(1.3 * breath, 0.72 * breath, 0.8);
    }

    // ----- eyes: blink, glance while thinking, color
    if (!still) {
      if (s.blinkAt < 0 && now >= s.nextBlink) s.blinkAt = now;
      if (s.blinkAt >= 0 && now - s.blinkAt > 200) {
        s.blinkAt = -1;
        s.nextBlink = now + nextBlinkDelay();
      }
    }
    const blink = still || s.blinkAt < 0 ? 0 : blinkAmount(now - s.blinkAt);
    const glanceSide = Math.floor(t / 1.6) % 3 === 0 ? -1 : 1;
    s.eyeX = damp(s.eyeX, still ? 0 : s.think * glanceSide * 0.07, 7, dt);
    s.eyeY = damp(s.eyeY, s.think * 0.05, 7, dt);
    if (eyes.current) eyes.current.position.set(s.eyeX, s.eyeY, 0);
    for (const eye of eyeMeshes.current) eye?.scale.set(1, Math.max(0.08, 1 - blink), 0.35);
    m.eyes.color.copy(AMBER_STRONG).lerp(INFO, s.think * 0.85).multiplyScalar(1.15 + s.speak * 0.15);
    m.eyeGlow.color.copy(m.eyes.color);
    m.eyeGlow.opacity = 0.35 + s.speak * 0.15 + s.amp * 0.3;

    // ----- mouth equalizer (real levels; a resting line otherwise; static mid bars when still)
    for (let i = 0; i < MOUTH_BARS; i++) {
      const source = bars ? (bars[i + 1] ?? 0) : 0;
      const target = state === "speaking" ? (still ? 0.55 - Math.abs(i - 3) * 0.1 : 0.12 + source) : 0.12;
      s.bars[i] = damp(s.bars[i], target, 22, dt);
      mouth.current[i]?.scale.set(1, Math.max(0.12, Math.min(1.35, s.bars[i] * 1.2)), 0.5);
    }
    m.mouth.color.copy(AMBER).multiplyScalar(0.35 + s.speak * 0.9);

    // ----- thinking: a scanning line sweeps the visor (static when still)
    if (scan.current) scan.current.rotation.x = still ? 0 : Math.sin(t * 2.4) * 0.34 - 0.08;
    m.scan.opacity = s.think * 0.5;

    // ----- listening: ear rings and halo pulse with the microphone level
    const hear = s.listen * (still ? 0.8 : 0.35 + s.amp * 1.6);
    m.ears.color.copy(AMBER).multiplyScalar(0.3 + hear);
    m.earGlow.opacity = Math.min(0.8, hear * 0.6);
    m.halo.opacity = 0.1 + hear * 0.35 + s.speak * 0.05;
    if (halo.current) halo.current.scale.setScalar(1 + (still ? 0 : s.listen * s.amp * 0.08));

    // ----- antenna tip: slow heartbeat, quicker while thinking
    const pulse = still ? 0.85 : 0.65 + 0.35 * Math.sin(t * (2 + s.think * 5));
    m.tip.color.copy(AMBER_STRONG).multiplyScalar(0.6 + pulse * 0.7 + s.think * 0.3);
    m.tipGlow.opacity = 0.25 + pulse * 0.35 + s.listen * 0.2;
    m.chest.color.copy(AMBER).multiplyScalar(0.4 + s.speak * 0.5 + s.listen * 0.4);

    if (!ready.current) {
      ready.current = true;
      performance.mark("avatar:first-frame");
      onReady();
    }
  });

  const eyeAt = (side: -1 | 1) => onHead(side * 0.3, 0.1, 1.02);
  const mouthAt = (i: number) => onHead((i - (MOUTH_BARS - 1) / 2) * 0.075, -0.27, 1.02);

  return (
    <group ref={rig} position={[0, 0.12, 0]}>
      {/* Back halo */}
      <mesh ref={halo} geometry={g.halo} material={m.halo} position={[0, 0.18, -0.9]} />

      {/* Shoulders, neck */}
      <group ref={shoulders} position={[0, -1.5, -0.1]} scale={[1.3, 0.72, 0.8]}>
        <mesh geometry={g.shoulders} material={m.shell} />
      </group>
      <mesh geometry={g.chestLight} material={m.chest} position={[0, -1.02, 0.6]} rotation={[0.9, 0, Math.PI / 2]} scale={[1, 1, 0.5]} />
      <mesh geometry={g.neck} material={m.trim} position={[0, -0.92, 0]} />
      <mesh geometry={g.neckRing} material={m.rim} position={[0, -0.8, 0]} rotation={[Math.PI / 2, 0, 0]} scale={0.86} />

      <group ref={head}>
        <mesh geometry={g.head} material={m.shell} scale={HEAD_SCALE} />
        <mesh geometry={g.visor} material={m.visor} scale={HEAD_SCALE} />

        {/* Scanning line (thinking) */}
        <group scale={HEAD_SCALE}>
          <mesh ref={scan} geometry={g.scan} material={m.scan} />
        </group>

        {/* Eyes */}
        <group ref={eyes}>
          {([-1, 1] as const).map((side, index) => {
            const at = eyeAt(side);
            return (
              <group key={side} position={at} rotation={[-0.1, side * 0.3, 0]}>
                <mesh
                  ref={(mesh) => {
                    eyeMeshes.current[index] = mesh;
                  }}
                  geometry={g.eye}
                  material={m.eyes}
                  scale={[1, 1, 0.35]}
                />
                <sprite material={m.eyeGlow} scale={[0.6, 0.6, 1]} position={[0, 0, 0.02]} />
              </group>
            );
          })}
        </group>

        {/* Equalizer mouth */}
        {Array.from({ length: MOUTH_BARS }, (_, i) => {
          const at = mouthAt(i);
          return (
            <mesh
              key={i}
              ref={(mesh) => {
                mouth.current[i] = mesh;
              }}
              geometry={g.mouthBar}
              material={m.mouth}
              position={at}
              rotation={[0.27, (i - (MOUTH_BARS - 1) / 2) * 0.075, 0]}
              scale={[1, 0.12, 0.5]}
            />
          );
        })}

        {/* Ear pods with listening rings (rotated so local -y points outward on both sides) */}
        {([-1, 1] as const).map((side) => (
          <group key={side} position={[side * 0.97, -0.02, -0.04]} rotation={[0, 0, side * (Math.PI / 2)]}>
            <mesh geometry={g.earPod} material={m.trim} />
            <mesh geometry={g.earRing} material={m.ears} position={[0, -0.085, 0]} rotation={[Math.PI / 2, 0, 0]} />
            <sprite material={m.earGlow} scale={[0.75, 0.75, 1]} position={[0, -0.12, 0]} />
          </group>
        ))}

        {/* Antenna, slightly off-center for an asymmetric silhouette */}
        <group position={[0.34, 0.8, -0.12]} rotation={[-0.12, 0, -0.3]}>
          <mesh geometry={g.antennaBase} material={m.trim} />
          <mesh geometry={g.antennaRod} material={m.trim} position={[0, 0.22, 0]} />
          <mesh geometry={g.antennaTip} material={m.tip} position={[0, 0.45, 0]} />
          <sprite material={m.tipGlow} scale={[0.42, 0.42, 1]} position={[0, 0.45, 0.01]} />
        </group>
      </group>
    </group>
  );
}
