"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import type { CityLive, CityModel } from "@/lib/city/state";
import { hourOf } from "@/lib/city/state";
import { clampToCity, collidesWithBuilding, type PlayLayout, type PlayTarget } from "@/lib/world3d/adapter";
import { consumeInteract, moveAxes, playInput } from "@/lib/world3d/input";

export interface PlayTelemetry {
  x: number;
  z: number;
  speed: number;
  nearTarget: string | null;
}

interface Props {
  model: CityModel;
  live: CityLive | null;
  simTime: string;
  layout: PlayLayout;
  objectiveIndex: number;
  onAdvance: (target: PlayTarget) => void;
  onTelemetry: (telemetry: PlayTelemetry) => void;
  quality: "low" | "high";
}

const dummy = new THREE.Object3D();
const tmpColor = new THREE.Color();

function Ground({ model }: { model: CityModel }) {
  const b = model.wire.bounds;
  const width = b.max_x - b.min_x;
  const depth = b.max_y - b.min_y;
  return (
    <mesh position={[(b.min_x + b.max_x) / 2, -0.18, (b.min_y + b.max_y) / 2]} receiveShadow>
      <boxGeometry args={[width + 80, 0.3, depth + 80]} />
      <meshStandardMaterial color="#05070b" roughness={0.9} metalness={0.1} />
    </mesh>
  );
}

function Roads({ model }: { model: CityModel }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    for (let i = 0; i < model.segmentCount; i += 1) {
      const o = i * 4;
      const ax = model.streetLines[o];
      const az = model.streetLines[o + 1];
      const bx = model.streetLines[o + 2];
      const bz = model.streetLines[o + 3];
      const dx = bx - ax;
      const dz = bz - az;
      const length = Math.max(1, Math.hypot(dx, dz));
      dummy.position.set((ax + bx) / 2, 0.02, (az + bz) / 2);
      dummy.rotation.set(0, -Math.atan2(dz, dx), 0);
      dummy.scale.set(length, 0.12, Math.max(3, model.streetWidth[i]));
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  }, [model]);
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, model.segmentCount]} receiveShadow>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="#121923" roughness={0.64} metalness={0.32} />
    </instancedMesh>
  );
}

function Buildings({ model }: { model: CityModel }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    for (let i = 0; i < model.buildings.length; i += 1) {
      const building = model.buildings[i];
      dummy.position.set(building.x, building.height / 2, building.y);
      dummy.rotation.set(0, -building.angle, 0);
      dummy.scale.set(building.width, Math.max(2.5, building.height), building.depth);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
      const hue = (building.district * 0.071 + (building.kind.length % 7) * 0.019) % 1;
      tmpColor.setHSL(0.55 + hue * 0.12, 0.22, 0.13 + (building.floors % 4) * 0.018);
      mesh.setColorAt(i, tmpColor);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [model]);
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, model.buildings.length]} castShadow receiveShadow>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial vertexColors roughness={0.54} metalness={0.28} emissive="#060a10" emissiveIntensity={0.45} />
    </instancedMesh>
  );
}

function Population({ model, live }: { model: CityModel; live: CityLive | null }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const lastTick = useRef(-2);

  useFrame(() => {
    const mesh = ref.current;
    if (!mesh || !live || live.tick === lastTick.current) return;
    lastTick.current = live.tick;
    let shown = 0;
    for (let slot = 0; slot < live.count && shown < 6000; slot += 1) {
      if (!live.live[slot]) continue;
      const buildingIndex = live.building[slot];
      if (buildingIndex < 0 || buildingIndex >= model.buildings.length) continue;
      const building = model.buildings[buildingIndex];
      const seed = ((slot + 1) * 2654435761) >>> 0;
      const jx = (((seed & 1023) / 1023) - 0.5) * Math.min(7, building.width * 0.45);
      const jz = ((((seed >>> 10) & 1023) / 1023) - 0.5) * Math.min(7, building.depth * 0.45);
      dummy.position.set(building.x + jx, building.height + 1.1 + (slot % 3) * 0.2, building.y + jz);
      dummy.rotation.set(0, 0, 0);
      dummy.scale.setScalar(live.isDerived(slot) ? 0.7 : 0.95);
      dummy.updateMatrix();
      mesh.setMatrixAt(shown, dummy.matrix);
      mesh.setColorAt(shown, tmpColor.set(live.isDerived(slot) ? "#7d64ff" : "#48f5d0"));
      shown += 1;
    }
    mesh.count = shown;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, 6000]} frustumCulled={false}>
      <sphereGeometry args={[0.75, 6, 5]} />
      <meshBasicMaterial vertexColors transparent opacity={0.85} />
    </instancedMesh>
  );
}

function WaspAgent() {
  const wings = useRef<THREE.Group>(null);
  useFrame((state) => {
    if (!wings.current) return;
    const flap = Math.sin(state.clock.elapsedTime * 24) * 0.28;
    wings.current.children.forEach((child, index) => {
      child.rotation.z = (index === 0 ? 1 : -1) * (0.5 + flap);
    });
  });
  return (
    <group scale={2.4}>
      <mesh position={[0, 1.5, 0]} castShadow><sphereGeometry args={[0.55, 12, 9]} /><meshStandardMaterial color="#ffcb22" roughness={0.32} metalness={0.42} /></mesh>
      <mesh position={[0, 0.7, 0.15]} castShadow><sphereGeometry args={[0.7, 12, 9]} /><meshStandardMaterial color="#151318" roughness={0.42} metalness={0.55} /></mesh>
      <mesh position={[0, -0.05, 0.3]} rotation={[0.8, 0, 0]} castShadow><coneGeometry args={[0.48, 1.5, 10]} /><meshStandardMaterial color="#f6a700" roughness={0.36} metalness={0.35} /></mesh>
      <mesh position={[-0.21, 1.7, 0.48]}><sphereGeometry args={[0.11, 8, 6]} /><meshBasicMaterial color="#39e6ff" /></mesh>
      <mesh position={[0.21, 1.7, 0.48]}><sphereGeometry args={[0.11, 8, 6]} /><meshBasicMaterial color="#39e6ff" /></mesh>
      <group ref={wings} position={[0, 0.9, -0.15]}>
        <mesh position={[-0.55, 0, 0]} rotation={[0.2, 0.1, 0.6]}><boxGeometry args={[1.25, 0.05, 0.55]} /><meshPhysicalMaterial color="#c9f8ff" transparent opacity={0.36} roughness={0.1} transmission={0.35} /></mesh>
        <mesh position={[0.55, 0, 0]} rotation={[0.2, -0.1, -0.6]}><boxGeometry args={[1.25, 0.05, 0.55]} /><meshPhysicalMaterial color="#c9f8ff" transparent opacity={0.36} roughness={0.1} transmission={0.35} /></mesh>
      </group>
    </group>
  );
}

function Targets({ layout, objectiveIndex }: { layout: PlayLayout; objectiveIndex: number }) {
  return (
    <>
      {layout.targets.map((target, index) => {
        const active = index === objectiveIndex;
        const done = index < objectiveIndex;
        return (
          <group key={target.id} position={[target.x, 0.08, target.z]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[active ? 4.2 : 2.2, active ? 5 : 2.7, 40]} />
              <meshBasicMaterial color={done ? "#1f6c5d" : target.color} transparent opacity={active ? 0.95 : 0.28} depthWrite={false} />
            </mesh>
            {active && (
              <mesh position={[0, 6, 0]}>
                <cylinderGeometry args={[0.16, 0.55, 12, 10]} />
                <meshBasicMaterial color={target.color} transparent opacity={0.28} depthWrite={false} blending={THREE.AdditiveBlending} />
              </mesh>
            )}
          </group>
        );
      })}
    </>
  );
}

function Rain({ player, quality }: { player: React.RefObject<THREE.Group | null>; quality: "low" | "high" }) {
  const count = quality === "high" ? 900 : 320;
  const points = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const values = new Float32Array(count * 3);
    for (let i = 0; i < count; i += 1) {
      values[i * 3] = (Math.random() - 0.5) * 220;
      values[i * 3 + 1] = Math.random() * 110 + 5;
      values[i * 3 + 2] = (Math.random() - 0.5) * 220;
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
      if (array[i * 3 + 1] < 0) array[i * 3 + 1] += 115;
    }
    obj.position.set(anchor.position.x, 0, anchor.position.z);
    obj.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={points}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[positions, 3]} /></bufferGeometry>
      <pointsMaterial color="#9ec7ff" size={0.38} transparent opacity={0.52} depthWrite={false} />
    </points>
  );
}

function PlayerDriver({ model, layout, objectiveIndex, onAdvance, onTelemetry, quality }: Omit<Props, "live" | "simTime">) {
  const player = useRef<THREE.Group>(null);
  const { camera } = useThree();
  const telemAccumulator = useRef(0);
  const position = useRef(new THREE.Vector3(layout.spawn.x, 0.3, layout.spawn.z));
  const velocity = useRef(new THREE.Vector2());

  useEffect(() => {
    position.current.set(layout.spawn.x, 0.3, layout.spawn.z);
  }, [layout.spawn.x, layout.spawn.z]);

  useFrame((_, rawDt) => {
    const dt = Math.min(rawDt, 0.05);
    const axes = moveAxes();
    const moving = Math.hypot(axes.x, axes.z) > 0.02;
    const maxSpeed = playInput.sprint ? 78 : 46;
    const desiredX = axes.x * maxSpeed;
    const desiredZ = axes.z * maxSpeed;
    const response = 1 - Math.exp(-dt * 8.5);
    velocity.current.x += (desiredX - velocity.current.x) * response;
    velocity.current.y += (desiredZ - velocity.current.y) * response;
    if (!moving) {
      velocity.current.multiplyScalar(Math.exp(-dt * 7));
    }

    const pos = position.current;
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
      const speed = velocity.current.length();
      if (speed > 2) player.current.rotation.y = Math.atan2(velocity.current.x, velocity.current.y);
    }

    const target = layout.targets[objectiveIndex] ?? null;
    const distance = target ? Math.hypot(pos.x - target.x, pos.z - target.z) : Number.POSITIVE_INFINITY;
    if (target && distance < 10 && consumeInteract()) onAdvance(target);

    const desiredCamera = new THREE.Vector3(pos.x + 115, 145, pos.z + 115);
    camera.position.lerp(desiredCamera, 1 - Math.exp(-dt * 5.5));
    camera.lookAt(pos.x, 0, pos.z);
    if (camera instanceof THREE.OrthographicCamera) {
      camera.zoom += ((quality === "high" ? 1.9 : 1.65) - camera.zoom) * (1 - Math.exp(-dt * 4));
      camera.updateProjectionMatrix();
    }

    telemAccumulator.current += dt;
    if (telemAccumulator.current >= 0.1) {
      telemAccumulator.current = 0;
      onTelemetry({ x: pos.x, z: pos.z, speed: velocity.current.length(), nearTarget: target && distance < 10 ? target.id : null });
    }
  });

  return (
    <>
      <group ref={player} position={[layout.spawn.x, 0.3, layout.spawn.z]}><WaspAgent /></group>
      <Rain player={player} quality={quality} />
    </>
  );
}

function Scene({ model, live, simTime, layout, objectiveIndex, onAdvance, onTelemetry, quality }: Props) {
  const hour = hourOf(simTime);
  const daylight = Math.max(0, Math.sin(((hour - 6) / 12) * Math.PI));
  const sky = daylight * 0.38 + 0.08;
  return (
    <>
      <fog attach="fog" args={["#05070c", 180, quality === "high" ? 760 : 520]} />
      <ambientLight intensity={0.18 + sky * 0.5} />
      <directionalLight position={[120, 220, 80]} intensity={0.45 + daylight * 1.4} color={daylight > 0.25 ? "#dce9ff" : "#7285b8"} castShadow={quality === "high"} />
      <pointLight position={[layout.spawn.x, 28, layout.spawn.z]} color="#b44dff" intensity={18} distance={100} />
      <Ground model={model} />
      <Roads model={model} />
      <Buildings model={model} />
      <Population model={model} live={live} />
      <Targets layout={layout} objectiveIndex={objectiveIndex} />
      <PlayerDriver model={model} layout={layout} objectiveIndex={objectiveIndex} onAdvance={onAdvance} onTelemetry={onTelemetry} quality={quality} />
    </>
  );
}

export default function HydraPlayScene(props: Props) {
  return (
    <Canvas
      className="play-canvas"
      orthographic
      camera={{ position: [props.layout.spawn.x + 115, 145, props.layout.spawn.z + 115], zoom: 1.7, near: 0.1, far: 3000 }}
      dpr={props.quality === "high" ? [1, 1.6] : [0.75, 1]}
      gl={{ antialias: props.quality === "high", powerPreference: "high-performance" }}
      shadows={props.quality === "high"}
    >
      <Scene {...props} />
    </Canvas>
  );
}
