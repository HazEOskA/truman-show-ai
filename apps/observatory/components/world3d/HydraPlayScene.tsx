"use client";

/**
 * The mission's viewport.
 *
 * Everything structural — ground, districts, streets, cubes, dots, light — comes from
 * `CityLayers`, which is the same geometry the Map view draws. What this file adds is only
 * what a *mission* needs on top of a city: the agent, the station pylons, the camera that
 * follows, and an autopilot.
 *
 * The autopilot exists for the jury. A demo that requires the person judging it to be good
 * at WASD is a demo about WASD; with autopilot on, the agent walks its own route and the
 * jury reads. Keys still work at any moment and quietly take over.
 */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { CityBuildings, CityCitizens, CityGround, CityLight, CityStreets, DistrictPlates, LandUse } from "@/components/world3d/CityLayers";
import type { CityLive, CityModel } from "@/lib/city/state";
import { hourOf } from "@/lib/city/state";
import { clampToCity, collidesWithBuilding, type PlayLayout, type PlayTarget } from "@/lib/world3d/adapter";
import { consumeInteract, moveAxes, playInput } from "@/lib/world3d/input";
import { buildStreetGraph, routeBetween, type Point } from "@/lib/world3d/route";

export interface PlayTelemetry {
  x: number;
  z: number;
  speed: number;
  distance: number;
  nearTarget: string | null;
}

interface Props {
  model: CityModel;
  live: CityLive | null;
  simTime: string;
  layout: PlayLayout;
  objectiveIndex: number;
  /** True while a dossier is open: the agent holds position and the camera drifts closer. */
  paused: boolean;
  autopilot: boolean;
  onAdvance: (target: PlayTarget) => void;
  onTelemetry: (telemetry: PlayTelemetry) => void;
  quality: "low" | "high";
}

/** How close the agent must be for a station to accept it. */
const REACH = 14;

/** How close to a waypoint counts as having reached it. */
const WAYPOINT_REACH = 16;

/**
 * Local steering toward the next waypoint.
 *
 * The route itself comes from the street graph (`lib/world3d/route.ts`), so this only has to
 * cover the last few metres onto and off the road, where a doorway or a kerb can still be in
 * the way. The heading is probed a short distance ahead and, if blocked, fanned aside --
 * nearly a full turn, because the way out of an alcove is often backwards.
 */
function steer(model: CityModel, pos: Point, target: Point): Point {
  const heading = towards(pos, target);
  if (isClear(model, pos, heading)) return heading;
  for (const angle of [0.5, -0.5, 1, -1, 1.5, -1.5, 2, -2, 2.6, -2.6, 3.1]) {
    const turned = rotate(heading, angle);
    if (isClear(model, pos, turned)) return turned;
  }
  return heading;
}

function towards(from: Point, to: Point): Point {
  const length = Math.max(1, Math.hypot(to.x - from.x, to.z - from.z));
  return { x: (to.x - from.x) / length, z: (to.z - from.z) / length };
}

function rotate(v: Point, angle: number): Point {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  return { x: v.x * cos - v.z * sin, z: v.x * sin + v.z * cos };
}

function isClear(model: CityModel, pos: Point, dir: Point, probe = 14): boolean {
  return !collidesWithBuilding(model, pos.x + dir.x * probe, pos.z + dir.z * probe, 2.6);
}

function near(a: Point, b: Point, radius: number): boolean {
  return Math.hypot(a.x - b.x, a.z - b.z) < radius;
}

// -- the agent --------------------------------------------------------------------------

/**
 * OSA — the audit drone.
 *
 * A wasp, because the operator's callsign is one, and because a small fast thing with an
 * obvious front reads at this camera distance where a humanoid would be four grey pixels.
 */
function WaspAgent({ moving }: { moving: boolean }) {
  const wings = useRef<THREE.Group>(null);
  const body = useRef<THREE.Group>(null);
  useFrame((state) => {
    const flap = Math.sin(state.clock.elapsedTime * (moving ? 30 : 18)) * 0.3;
    wings.current?.children.forEach((child, index) => {
      child.rotation.z = (index === 0 ? 1 : -1) * (0.5 + flap);
    });
    if (body.current) {
      body.current.position.y = Math.sin(state.clock.elapsedTime * 3.2) * 0.28;
      body.current.rotation.x = moving ? 0.22 : 0.05;
    }
  });
  return (
    <group scale={2.4} ref={body}>
      <mesh position={[0, 1.5, 0]}><sphereGeometry args={[0.55, 12, 9]} /><meshStandardMaterial color="#ffcb22" roughness={0.32} metalness={0.42} /></mesh>
      <mesh position={[0, 0.7, 0.15]}><sphereGeometry args={[0.7, 12, 9]} /><meshStandardMaterial color="#151318" roughness={0.42} metalness={0.55} /></mesh>
      <mesh position={[0, -0.05, 0.3]} rotation={[0.8, 0, 0]}><coneGeometry args={[0.48, 1.5, 10]} /><meshStandardMaterial color="#f6a700" roughness={0.36} metalness={0.35} /></mesh>
      <mesh position={[-0.21, 1.7, 0.48]}><sphereGeometry args={[0.11, 8, 6]} /><meshBasicMaterial color="#39e6ff" /></mesh>
      <mesh position={[0.21, 1.7, 0.48]}><sphereGeometry args={[0.11, 8, 6]} /><meshBasicMaterial color="#39e6ff" /></mesh>
      <group ref={wings} position={[0, 0.9, -0.15]}>
        <mesh position={[-0.55, 0, 0]} rotation={[0.2, 0.1, 0.6]}><boxGeometry args={[1.25, 0.05, 0.55]} /><meshPhysicalMaterial color="#c9f8ff" transparent opacity={0.36} roughness={0.1} transmission={0.35} /></mesh>
        <mesh position={[0.55, 0, 0]} rotation={[0.2, -0.1, -0.6]}><boxGeometry args={[1.25, 0.05, 0.55]} /><meshPhysicalMaterial color="#c9f8ff" transparent opacity={0.36} roughness={0.1} transmission={0.35} /></mesh>
      </group>
      <pointLight position={[0, 1.4, 0]} color="#ffd06a" intensity={9} distance={46} />
    </group>
  );
}

// -- stations ---------------------------------------------------------------------------

/** A station's code, drawn to a canvas and hung in the air above its pylon. */
function CodeLabel({ text, colour, y }: { text: string; colour: string; y: number }) {
  const texture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 512;
    canvas.height = 128;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.font = "700 76px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = colour;
      ctx.shadowColor = colour;
      ctx.shadowBlur = 26;
      ctx.fillText(text, 256, 68);
    }
    const map = new THREE.CanvasTexture(canvas);
    map.anisotropy = 4;
    return map;
  }, [text, colour]);

  useEffect(() => () => texture.dispose(), [texture]);

  return (
    <sprite position={[0, y, 0]} scale={[36, 9, 1]}>
      <spriteMaterial map={texture} transparent depthWrite={false} depthTest={false} />
    </sprite>
  );
}

/**
 * The pylons.
 *
 * Three states, readable from across the city: the station you are heading to burns and
 * pulses, the ones you have logged are quiet green rings, the ones ahead are faint outlines.
 * Nothing here is decoration — it is the mission's progress bar, drawn into the world.
 */
function Stations({ layout, objectiveIndex }: { layout: PlayLayout; objectiveIndex: number }) {
  const pulse = useRef<THREE.Group>(null);
  useFrame((state) => {
    if (!pulse.current) return;
    const t = (state.clock.elapsedTime % 2) / 2;
    pulse.current.scale.setScalar(1 + t * 1.7);
    const material = (pulse.current.children[0] as THREE.Mesh)?.material as THREE.MeshBasicMaterial;
    if (material) material.opacity = 0.55 * (1 - t);
  });

  return (
    <>
      {layout.targets.map((target, index) => {
        const active = index === objectiveIndex;
        const done = index < objectiveIndex;
        const colour = done ? "#3f8f6a" : target.colour;
        return (
          <group key={target.id} position={[target.x, 0.2, target.z]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[active ? 8 : 4.4, active ? 9.4 : 5.1, 48]} />
              <meshBasicMaterial color={colour} transparent opacity={active ? 0.95 : done ? 0.5 : 0.24} depthWrite={false} />
            </mesh>
            {active && (
              <>
                <mesh position={[0, 34, 0]}>
                  <cylinderGeometry args={[0.5, 3.4, 68, 12, 1, true]} />
                  <meshBasicMaterial color={colour} transparent opacity={0.2} depthWrite={false} side={THREE.DoubleSide} blending={THREE.AdditiveBlending} />
                </mesh>
                <group ref={pulse}>
                  <mesh rotation={[-Math.PI / 2, 0, 0]}>
                    <ringGeometry args={[9.4, 10.6, 48]} />
                    <meshBasicMaterial color={colour} transparent opacity={0.5} depthWrite={false} />
                  </mesh>
                </group>
                <pointLight position={[0, 16, 0]} color={colour} intensity={26} distance={130} />
              </>
            )}
            <CodeLabel text={done ? `${target.station.code} ✓` : target.station.code} colour={colour} y={active ? 78 : 26} />
          </group>
        );
      })}
    </>
  );
}

// -- weather ----------------------------------------------------------------------------

function Rain({ player, quality }: { player: React.RefObject<THREE.Group | null>; quality: "low" | "high" }) {
  const count = quality === "high" ? 900 : 320;
  const points = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const values = new Float32Array(count * 3);
    for (let i = 0; i < count; i += 1) {
      values[i * 3] = (Math.random() - 0.5) * 260;
      values[i * 3 + 1] = Math.random() * 120 + 5;
      values[i * 3 + 2] = (Math.random() - 0.5) * 260;
    }
    return values;
  }, [count]);

  useFrame((_, dt) => {
    const obj = points.current;
    const anchor = player.current;
    if (!obj || !anchor) return;
    const array = obj.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < count; i += 1) {
      array[i * 3 + 1] -= dt * 95;
      if (array[i * 3 + 1] < 0) array[i * 3 + 1] += 125;
    }
    obj.position.set(anchor.position.x, 0, anchor.position.z);
    obj.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={points}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[positions, 3]} /></bufferGeometry>
      <pointsMaterial color="#9ec7ff" size={0.42} transparent opacity={0.42} depthWrite={false} />
    </points>
  );
}

// -- driving ----------------------------------------------------------------------------

function PlayerDriver({
  model,
  layout,
  objectiveIndex,
  paused,
  autopilot,
  onAdvance,
  onTelemetry,
  quality
}: Omit<Props, "live" | "simTime">) {
  const player = useRef<THREE.Group>(null);
  const { camera } = useThree();
  const telemetry = useRef(0);
  const position = useRef(new THREE.Vector3(layout.spawn.x, 0.3, layout.spawn.z));
  const velocity = useRef(new THREE.Vector2());
  const movingRef = useRef(false);
  const arrivedAt = useRef<string | null>(null);

  // The street graph is built once per world; the route along it is planned once per leg.
  const graph = useMemo(() => buildStreetGraph(model), [model]);
  const path = useRef<Point[]>([]);
  const waypoint = useRef(0);
  /** Where the agent was when it last made progress, and when that was. */
  const stall = useRef({ x: 0, z: 0, at: 0 });

  useEffect(() => {
    position.current.set(layout.spawn.x, 0.3, layout.spawn.z);
  }, [layout.spawn.x, layout.spawn.z]);

  // A new leg is a new plan, made from wherever the agent is standing now.
  useEffect(() => {
    const target = layout.targets[objectiveIndex];
    if (!target) {
      path.current = [];
      return;
    }
    const from = { x: position.current.x, z: position.current.z };
    const planned = routeBetween(graph, from, { x: target.x, z: target.z });
    // An unroutable pair (a world whose streets do not connect two quarters) falls back to
    // walking straight at the station rather than refusing to move.
    path.current = planned.length ? planned : [{ x: target.x, z: target.z }];
    waypoint.current = 0;
    stall.current = { x: from.x, z: from.z, at: 0 };
  }, [graph, layout, objectiveIndex]);

  useFrame((state, rawDt) => {
    const dt = Math.min(rawDt, 0.05);
    const now = state.clock.elapsedTime;
    const target = layout.targets[objectiveIndex] ?? null;
    const pos = position.current;
    const distance = target ? Math.hypot(pos.x - target.x, pos.z - target.z) : Number.POSITIVE_INFINITY;

    const manual = moveAxes();
    const driving = Math.hypot(manual.x, manual.z) > 0.02;
    let axes = manual;

    // Autopilot never fights the operator: the moment a key is held, manual input wins.
    if (!driving && autopilot && target && !paused && distance > REACH * 0.55) {
      // Walk the planned waypoints, dropping each one as it is reached. The last entry is
      // the station itself, so the final approach is a straight line to the door.
      while (
        waypoint.current < path.current.length - 1 &&
        near(pos, path.current[waypoint.current], WAYPOINT_REACH)
      ) {
        waypoint.current += 1;
      }
      // Watchdog. A waypoint the agent cannot actually reach -- a node the generator put
      // inside a block, a doorway too tight for its collision radius -- would otherwise hold
      // the mission still in front of the jury. Three seconds without moving four metres and
      // the agent gives up on this waypoint and aims at the next one.
      if (Math.hypot(pos.x - stall.current.x, pos.z - stall.current.z) > 4) {
        stall.current = { x: pos.x, z: pos.z, at: now };
      } else if (now - stall.current.at > 3) {
        if (waypoint.current < path.current.length - 1) waypoint.current += 1;
        stall.current = { x: pos.x, z: pos.z, at: now };
      }

      const next = path.current[waypoint.current] ?? { x: target.x, z: target.z };
      axes = steer(model, pos, next);
    }
    if (paused) axes = { x: 0, z: 0 };

    const moving = Math.hypot(axes.x, axes.z) > 0.02;
    movingRef.current = moving;
    const maxSpeed = playInput.sprint ? 82 : autopilot && !driving ? 52 : 46;
    const response = 1 - Math.exp(-dt * 8.5);
    velocity.current.x += (axes.x * maxSpeed - velocity.current.x) * response;
    velocity.current.y += (axes.z * maxSpeed - velocity.current.y) * response;
    if (!moving) velocity.current.multiplyScalar(Math.exp(-dt * 7));

    const nextX = pos.x + velocity.current.x * dt;
    if (!collidesWithBuilding(model, nextX, pos.z)) pos.x = nextX;
    else velocity.current.x = 0;
    const nextZ = pos.z + velocity.current.y * dt;
    if (!collidesWithBuilding(model, pos.x, nextZ)) pos.z = nextZ;
    else velocity.current.y = 0;
    const clamped = clampToCity(model, pos.x, pos.z);
    pos.x = clamped.x;
    pos.z = clamped.z;

    if (player.current) {
      player.current.position.copy(pos);
      if (velocity.current.length() > 2) {
        player.current.rotation.y = Math.atan2(velocity.current.x, velocity.current.y);
      }
    }

    // Arrival. Manual play still asks for E; autopilot logs the station itself, once —
    // `arrivedAt` is what stops it from re-triggering while the dossier is open.
    if (target && distance < REACH && !paused) {
      const wanted = consumeInteract();
      const auto = autopilot && arrivedAt.current !== target.id;
      if (wanted || auto) {
        arrivedAt.current = target.id;
        onAdvance(target);
      }
    } else {
      consumeInteract();
    }

    // Camera. Isometric and high while walking, lower and closer while reading a dossier:
    // the city stays the backdrop of the argument rather than disappearing behind a panel.
    const zoomTo = (quality === "high" ? 1.9 : 1.65) * (paused ? 1.45 : 1);
    const lift = paused ? 0.72 : 1;
    const desired = new THREE.Vector3(pos.x + 115 * lift, 145 * lift, pos.z + 115 * lift);
    camera.position.lerp(desired, 1 - Math.exp(-dt * (paused ? 2.4 : 5.5)));
    camera.lookAt(pos.x, 0, pos.z);
    if (camera instanceof THREE.OrthographicCamera) {
      camera.zoom += (zoomTo - camera.zoom) * (1 - Math.exp(-dt * 3));
      camera.updateProjectionMatrix();
    }

    telemetry.current += dt;
    if (telemetry.current >= 0.12) {
      telemetry.current = 0;
      onTelemetry({
        x: pos.x,
        z: pos.z,
        speed: velocity.current.length(),
        distance: Number.isFinite(distance) ? distance : 0,
        nearTarget: target && distance < REACH ? target.id : null
      });
    }
  });

  return (
    <>
      <group ref={player} position={[layout.spawn.x, 0.3, layout.spawn.z]}>
        <WaspAgent moving={movingRef.current} />
      </group>
      <Rain player={player} quality={quality} />
    </>
  );
}

// -- scene ------------------------------------------------------------------------------

function Scene(props: Props) {
  const { model, live, simTime, quality } = props;
  const hour = hourOf(simTime);
  const high = quality === "high";
  return (
    <>
      <CityLight model={model} hour={hour} fogNear={320} fogFar={high ? 1600 : 1000} />
      <CityGround model={model} />
      <DistrictPlates model={model} />
      <LandUse model={model} />
      <CityStreets model={model} />
      <CityBuildings model={model} live={live} hour={hour} />
      <CityCitizens model={model} live={live} max={high ? 6000 : 2200} />
      <Stations layout={props.layout} objectiveIndex={props.objectiveIndex} />
      <PlayerDriver {...props} />
    </>
  );
}

export default function HydraPlayScene(props: Props) {
  return (
    <Canvas
      className="play-canvas"
      orthographic
      camera={{ position: [props.layout.spawn.x + 115, 145, props.layout.spawn.z + 115], zoom: 1.7, near: 0.1, far: 6000 }}
      dpr={props.quality === "high" ? [1, 1.6] : [0.75, 1]}
      gl={{ antialias: props.quality === "high", powerPreference: "high-performance" }}
    >
      <Scene {...props} />
    </Canvas>
  );
}
