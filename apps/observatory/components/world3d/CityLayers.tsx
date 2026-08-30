"use client";

/**
 * The city, in cubes and dots.
 *
 * One set of meshes draws Hydra everywhere it appears in three dimensions: the jury mission
 * walks through it, the Map view looks down on it, and both are looking at the *same*
 * geometry read from the same projection. That is the point of this file existing at all —
 * a second, prettier city built for the demo would be the one thing this project must never
 * ship.
 *
 * The vocabulary is deliberately the one everybody already knows from a city builder:
 *
 * * **cubes** are buildings, coloured by what they are for and as tall as their floor count,
 * * **dots** are people, one per simulated individual, standing at the address the world
 *   says they are at and walking to the next one when the world moves them,
 * * **plates** are districts, **ribbons** are streets, **patches** are parks and water.
 *
 * Nothing here decides anything. Every position, height, kind and occupancy is read from
 * `CityModel` (the projection) and `CityLive` (the frame stream); this module only chooses
 * how to draw them.
 *
 * Everything is instanced. Six hundred buildings and six thousand residents are two draw
 * calls, not six thousand six hundred, and the per-frame work is writing matrices into a
 * buffer rather than walking a scene graph.
 */

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import type { BuildingView, CityLive, CityModel } from "@/lib/city/state";
import {
  AGENT_ASLEEP,
  AGENT_AWAKE,
  AGENT_DORMANT,
  AGENT_IDLE,
  AGENT_PERSISTENT,
  GROUND,
  OUTSIDE
} from "@/lib/city/palette";
import { ACTIVITY, TIER } from "@/lib/city/types";
import {
  atmosphere,
  brighten,
  colour,
  districtColour,
  landUseColour,
  streetColour,
  zoneColour,
  type Atmosphere
} from "@/lib/world3d/theme";

const dummy = new THREE.Object3D();
const tint = new THREE.Color();

/** How long a person is shown walking between two addresses, in milliseconds. */
const TRAVEL_MS = 2600;

// -- ground -----------------------------------------------------------------------------

export function CityGround({ model }: { model: CityModel }) {
  const b = model.wire.bounds;
  const width = b.max_x - b.min_x;
  const depth = b.max_y - b.min_y;
  return (
    <mesh
      position={[(b.min_x + b.max_x) / 2, -0.6, (b.min_y + b.max_y) / 2]}
      rotation={[-Math.PI / 2, 0, 0]}
      receiveShadow
    >
      {/* Generous on purpose: the plate has to reach past the horizon at every camera
          angle, or the city ends in a visible edge with sky underneath it. */}
      <planeGeometry args={[(width + depth) * 2.5, (width + depth) * 2.5]} />
      <meshStandardMaterial color={colour(OUTSIDE)} roughness={1} metalness={0} />
    </mesh>
  );
}

/**
 * District plates.
 *
 * A city read from above is unreadable without them: buildings alone are a scatter of
 * boxes, and it is the coloured ground under them that says *this is the port, that is the
 * elite quarter*. `paint` lets the Map view replace the zoning colour with a data layer
 * without any of the geometry being rebuilt.
 */
export function DistrictPlates({
  model,
  paint,
  opacity = 1,
  highlight = null,
  onPick
}: {
  model: CityModel;
  paint?: (districtId: string, index: number) => number | null;
  opacity?: number;
  /** District id drawn lifted and outlined — the one a viewer has selected. */
  highlight?: string | null;
  onPick?: (districtId: string, index: number) => void;
}) {
  // Built once per projection. District outlines are fixed for the life of a world, so the
  // geometry is too -- rebuilding it every frame would be the most expensive way to draw a
  // shape that has not moved since genesis.
  const plates = useMemo(
    () =>
      model.wire.districts.map((district) => {
        const shape = new THREE.Shape();
        const points = district.polygon;
        // The projection's y is the scene's z, so the shape is built mirrored and then laid
        // flat by a -90 degree turn about x, which puts it back the right way round.
        shape.moveTo(points[0], -points[1]);
        for (let i = 2; i < points.length; i += 2) shape.lineTo(points[i], -points[i + 1]);
        shape.closePath();
        return new THREE.ShapeGeometry(shape);
      }),
    [model]
  );

  useLayoutEffect(() => () => plates.forEach((geometry) => geometry.dispose()), [plates]);

  return (
    <group>
      {model.wire.districts.map((district, index) => {
        const painted = paint?.(district.id, index) ?? null;
        const selected = highlight === district.id;
        return (
          <mesh
            key={district.id}
            geometry={plates[index]}
            rotation={[-Math.PI / 2, 0, 0]}
            // Plates are coplanar, so they are stacked a millimetre apart: two polygons at
            // exactly the same height flicker against each other as the camera turns.
            position={[0, (selected ? 0.5 : 0.02) + index * 0.001, 0]}
            receiveShadow
            onClick={onPick ? (event) => { event.stopPropagation(); onPick(district.id, index); } : undefined}
          >
            <meshStandardMaterial
              color={colour(painted ?? districtColour(district.kind))}
              roughness={0.95}
              metalness={0.02}
              transparent={opacity < 1}
              opacity={opacity}
              emissive={colour(selected ? 0x2a4c66 : 0x000000)}
              emissiveIntensity={selected ? 1 : 0}
            />
          </mesh>
        );
      })}
    </group>
  );
}

/**
 * Parks, plazas, yards and water.
 *
 * Small patches of colour, and the cheapest legibility in the whole scene: a green square
 * between two housing blocks is what makes a grid of cubes read as somewhere people live.
 */
export function LandUse({ model }: { model: CityModel }) {
  const parcels = model.wire.parcels;
  const groups = useMemo(() => {
    const byUse = new Map<string, number[]>();
    for (let i = 0; i < parcels.use.length; i += 1) {
      const use = parcels.uses[parcels.use[i]];
      if (use === "building" || use === "vacant") continue;
      const list = byUse.get(use) ?? [];
      list.push(i);
      byUse.set(use, list);
    }
    return [...byUse.entries()];
  }, [parcels]);

  return (
    <>
      {groups.map(([use, indices]) => (
        <ParcelPatch key={use} model={model} use={use} indices={indices} />
      ))}
    </>
  );
}

function ParcelPatch({
  model,
  use,
  indices
}: {
  model: CityModel;
  use: string;
  indices: number[];
}) {
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const rect = model.wire.parcels.rect;
    indices.forEach((parcel, slot) => {
      const o = parcel * 5;
      dummy.position.set(rect[o], 0.09, rect[o + 1]);
      dummy.rotation.set(-Math.PI / 2, 0, rect[o + 4]);
      dummy.scale.set(Math.max(1, rect[o + 2]), Math.max(1, rect[o + 3]), 1);
      dummy.updateMatrix();
      mesh.setMatrixAt(slot, dummy.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  }, [model, indices]);

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, indices.length]} receiveShadow>
      <planeGeometry args={[1, 1]} />
      <meshStandardMaterial color={colour(landUseColour(use))} roughness={0.9} metalness={0.02} />
    </instancedMesh>
  );
}

// -- streets ----------------------------------------------------------------------------

/**
 * Streets, one flat ribbon per segment, split by class so an arterial reads brighter than a
 * side street. The street grid is what turns a field of cubes into a city you can navigate,
 * so it is drawn above the district plate and never fogged out at close range.
 */
export function CityStreets({ model }: { model: CityModel }) {
  const byClass = useMemo(() => {
    const groups = new Map<number, number[]>();
    for (let i = 0; i < model.segmentCount; i += 1) {
      const list = groups.get(model.streetKlass[i]) ?? [];
      list.push(i);
      groups.set(model.streetKlass[i], list);
    }
    return [...groups.entries()];
  }, [model]);

  return (
    <>
      {byClass.map(([klass, segments]) => (
        <StreetRibbon key={klass} model={model} klass={klass} segments={segments} />
      ))}
    </>
  );
}

function StreetRibbon({
  model,
  klass,
  segments
}: {
  model: CityModel;
  klass: number;
  segments: number[];
}) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const name = model.wire.streets.klasses[klass] ?? "local";

  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    segments.forEach((segment, slot) => {
      const o = segment * 4;
      const ax = model.streetLines[o];
      const az = model.streetLines[o + 1];
      const bx = model.streetLines[o + 2];
      const bz = model.streetLines[o + 3];
      const length = Math.max(1, Math.hypot(bx - ax, bz - az));
      dummy.position.set((ax + bx) / 2, 0.14, (az + bz) / 2);
      dummy.rotation.set(-Math.PI / 2, 0, Math.atan2(bz - az, bx - ax));
      dummy.scale.set(length, Math.max(3.5, model.streetWidth[segment]), 1);
      dummy.updateMatrix();
      mesh.setMatrixAt(slot, dummy.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  }, [model, segments]);

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, segments.length]} receiveShadow>
      <planeGeometry args={[1, 1]} />
      <meshStandardMaterial
        color={colour(streetColour(name))}
        roughness={0.78}
        metalness={0.12}
        emissive={colour(streetColour(name))}
        emissiveIntensity={0.22}
      />
    </instancedMesh>
  );
}

// -- buildings --------------------------------------------------------------------------

export interface BuildingPaint {
  (building: BuildingView, index: number): number | null;
}

/**
 * The cubes.
 *
 * Height is the world's floor count times its storey height — nothing here is scaled for
 * drama — and the colour is what the building is *for*. Two instanced meshes are used, one
 * for the massing and one for a thin roof cap, because a flat-topped box lit from one side
 * reads as a smudge and a capped one reads as a building.
 */
export function CityBuildings({
  model,
  live,
  hour,
  paint,
  emissive = true
}: {
  model: CityModel;
  live?: CityLive | null;
  hour: number;
  paint?: BuildingPaint;
  emissive?: boolean;
}) {
  const body = useRef<THREE.InstancedMesh>(null);
  const roof = useRef<THREE.InstancedMesh>(null);
  const sky = atmosphere(hour);
  const count = model.buildings.length;

  useLayoutEffect(() => {
    const mesh = body.current;
    const cap = roof.current;
    if (!mesh || !cap) return;
    // The colour buffer is allocated here, before anything renders, rather than being left
    // to the first `setColorAt` below. See `ensureInstanceColour` for why that matters.
    ensureInstanceColour(mesh, count);
    ensureInstanceColour(cap, count);
    for (let i = 0; i < count; i += 1) {
      const building = model.buildings[i];
      const height = Math.max(3, building.height);
      dummy.position.set(building.x, height / 2, building.y);
      dummy.rotation.set(0, -building.angle, 0);
      dummy.scale.set(building.width, height, building.depth);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);

      dummy.position.set(building.x, height + 0.35, building.y);
      dummy.scale.set(building.width * 1.06, 0.7, building.depth * 1.06);
      dummy.updateMatrix();
      cap.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
    cap.instanceMatrix.needsUpdate = true;
  }, [model, count]);

  // Colour is recomputed when the light changes or a layer is painted, but the matrices are
  // not: the city does not move, and rebuilding six hundred transforms because dusk fell
  // would be work spent on nothing.
  useLayoutEffect(() => {
    const mesh = body.current;
    const cap = roof.current;
    if (!mesh || !cap) return;
    for (let i = 0; i < count; i += 1) {
      const building = model.buildings[i];
      const painted = paint?.(building, i) ?? null;
      const base = painted ?? zoneColour(building.kind);
      // Occupied buildings light their windows after dark. This is read from the frame
      // stream, so a block that empties out at 03:00 goes dark on its own.
      const occupancy = live && i < live.occupancy.length ? live.occupancy[i] : 0;
      const lit = occupancy > 0 && emissive ? sky.windowGlow : 0;
      tint.set(brighten(base, lit * 0.24));
      mesh.setColorAt(i, tint);
      tint.set(brighten(base, 0.1));
      cap.setColorAt(i, tint);
    }
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    if (cap.instanceColor) cap.instanceColor.needsUpdate = true;
  }, [model, count, paint, live?.tick, sky.windowGlow, emissive]);

  return (
    <group>
      <instancedMesh ref={body} args={[undefined, undefined, count]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial
          roughness={0.62}
          metalness={0.18}
          emissive={new THREE.Color(0x2b3350)}
          emissiveIntensity={emissive ? 0.3 + sky.windowGlow * 0.7 : 0.12}
        />
      </instancedMesh>
      <instancedMesh ref={roof} args={[undefined, undefined, count]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial roughness={0.85} metalness={0.05} />
      </instancedMesh>
    </group>
  );
}


/**
 * Give an instanced mesh its colour buffer before anything renders.
 *
 * Two traps live here, and this project fell into both.
 *
 * The first: three.js allocates `instanceColor` lazily on the first `setColorAt`, and a
 * buffer that appears after the material has compiled is not in the compiled shader.
 * Allocating up front removes that race.
 *
 * The second, and the one that painted every building in Hydra solid black: an instanced
 * material must **not** set `vertexColors`. That flag compiles `vColor *= color`, where
 * `color` is a *per-vertex* attribute a `BoxGeometry` does not have -- and an unbound
 * attribute reads as zero, so every instance multiplies itself down to black no matter what
 * `setColorAt` wrote. Per-instance colour needs no flag at all: three.js switches it on by
 * itself the moment `instanceColor` exists.
 */
function ensureInstanceColour(mesh: THREE.InstancedMesh, count: number): void {
  if (mesh.instanceColor && mesh.instanceColor.count >= count) return;
  const values = new Float32Array(count * 3).fill(1);
  mesh.instanceColor = new THREE.InstancedBufferAttribute(values, 3);
  mesh.instanceColor.setUsage(THREE.DynamicDrawUsage);
}

// -- people -----------------------------------------------------------------------------

/**
 * The dots.
 *
 * One per individually simulated resident, at the address the world put them at, walking
 * between addresses when the world moves them. The three palette rules the 2D view
 * established hold here too and matter more, because in 3D a dot is easy to over-sell:
 *
 * * **a derived position looks derived** — dimmer and smaller than an observed one,
 * * **cohorts are never drawn as dots**, because 45 000 statistical residents are not
 *   people you could click,
 * * **asleep is cold, awake is warm**, so the city visibly empties at night.
 */
export function CityCitizens({
  model,
  live,
  max = 6000,
  showDerived = true,
  size = 1
}: {
  model: CityModel;
  live: CityLive | null;
  max?: number;
  showDerived?: boolean;
  size?: number;
}) {
  const ref = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    if (ref.current) ensureInstanceColour(ref.current, max);
  }, [max]);

  useFrame(() => {
    const mesh = ref.current;
    if (!mesh || !live) return;
    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    let shown = 0;

    for (let slot = 0; slot < live.count && shown < max; slot += 1) {
      if (!live.live[slot]) continue;
      if (live.tier[slot] === TIER.COHORT) continue;
      const derived = live.isDerived(slot);
      if (derived && !showDerived) continue;

      const index = live.building[slot];
      if (index < 0 || index >= model.buildings.length) continue;
      const building = model.buildings[index];

      // A person the world has just moved is drawn walking from their previous doorway to
      // this one. The world publishes positions every few ticks; without this the city is a
      // slideshow of teleports.
      let x = building.entrance[0];
      let z = building.entrance[1];
      const previous = live.fromBuilding[slot];
      if (previous >= 0 && previous < model.buildings.length) {
        const t = ease(live.travel(slot, now, TRAVEL_MS));
        const from = model.buildings[previous];
        x = from.entrance[0] + (x - from.entrance[0]) * t;
        z = from.entrance[1] + (z - from.entrance[1]) * t;
      }

      // Everyone at one address would be one dot, so the crowd is spread over the doorway
      // by a hash of the slot: stable per person, so nobody jitters between frames.
      const seed = ((slot + 1) * 2654435761) >>> 0;
      const jx = ((seed & 1023) / 1023 - 0.5) * 7;
      const jz = (((seed >>> 10) & 1023) / 1023 - 0.5) * 7;
      const bob = live.isAsleep(slot) ? 0 : Math.sin(now * 0.003 + slot) * 0.22;

      dummy.position.set(x + jx, 1.1 + bob, z + jz);
      dummy.scale.setScalar((derived ? 0.62 : 0.95) * size);
      dummy.updateMatrix();
      mesh.setMatrixAt(shown, dummy.matrix);
      mesh.setColorAt(shown, tint.set(citizenColour(live, slot)));
      shown += 1;
    }

    mesh.count = shown;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, max]} frustumCulled={false}>
      <sphereGeometry args={[0.85, 8, 6]} />
      <meshBasicMaterial transparent opacity={0.92} />
    </instancedMesh>
  );
}

function citizenColour(live: CityLive, slot: number): number {
  if (live.isDerived(slot)) return AGENT_DORMANT;
  if (live.tier[slot] === TIER.PERSISTENT) return AGENT_PERSISTENT;
  switch (live.activity[slot]) {
    case ACTIVITY.SLEEP:
    case ACTIVITY.DORMANT:
      return AGENT_ASLEEP;
    case ACTIVITY.LIGHT_IDLE:
      return AGENT_IDLE;
    default:
      return AGENT_AWAKE;
  }
}

function ease(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}


// -- labels -----------------------------------------------------------------------------

/**
 * District names, hung over their centres.
 *
 * A city map without place names is a picture of a city. The sprites are re-scaled every
 * frame against the camera's zoom so a name stays the same size on screen whether the whole
 * region or one block is in view -- text that shrinks with the world becomes unreadable at
 * exactly the zoom where it is most needed.
 */
export function DistrictLabels({ model, pixels = 132 }: { model: CityModel; pixels?: number }) {
  const group = useRef<THREE.Group>(null);
  const { camera } = useThree();

  const sprites = useMemo(
    () =>
      model.wire.districts.map((district) => ({
        id: district.id,
        name: district.name.toUpperCase(),
        x: district.centre[0],
        z: district.centre[1],
        texture: textTexture(district.name.toUpperCase())
      })),
    [model]
  );

  useEffect(() => () => sprites.forEach((entry) => entry.texture.dispose()), [sprites]);

  useFrame(() => {
    const zoom = camera instanceof THREE.OrthographicCamera ? camera.zoom : 1;
    const width = pixels / Math.max(0.0001, zoom);
    group.current?.children.forEach((child) => child.scale.set(width, width * 0.25, 1));
  });

  return (
    <group ref={group}>
      {sprites.map((entry) => (
        <sprite key={entry.id} position={[entry.x, 60, entry.z]}>
          <spriteMaterial map={entry.texture} transparent depthWrite={false} depthTest={false} opacity={0.9} />
        </sprite>
      ))}
    </group>
  );
}

function textTexture(text: string): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.font = "600 54px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(226, 240, 255, 0.92)";
    ctx.shadowColor = "rgba(0, 0, 0, 0.9)";
    ctx.shadowBlur = 16;
    ctx.fillText(text, 256, 68);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.anisotropy = 4;
  return texture;
}

// -- light ------------------------------------------------------------------------------

/**
 * Sun, sky and fog for a simulated hour. One component, so every 3D view ages identically.
 *
 * Shadows are off. Hydra is eleven kilometres across and a building is thirty metres wide,
 * so a single directional shadow map spanning the city gives about six metres per texel --
 * coarser than the things casting into it. The result is not soft shadows, it is every wall
 * shadowing itself, which is what turned this scene's cubes black the first time it ran.
 * Hemisphere plus sun, with a lit roof cap for the top edge, reads the zoning better and
 * costs a fraction as much. Pass `shadows` only for a camera held close to the ground.
 */
export function CityLight({
  model,
  hour,
  shadows = false,
  fog = true,
  fogNear = 220,
  fogFar = 900
}: {
  model: CityModel;
  hour: number;
  shadows?: boolean;
  fog?: boolean;
  fogNear?: number;
  fogFar?: number;
}) {
  const sky: Atmosphere = atmosphere(hour);
  const b = model.wire.bounds;
  const cx = (b.min_x + b.max_x) / 2;
  const cz = (b.min_y + b.max_y) / 2;
  const span = Math.max(b.max_x - b.min_x, b.max_y - b.min_y);

  return (
    <>
      <color attach="background" args={[sky.sky]} />
      {fog && <fog attach="fog" args={[sky.fog, fogNear, fogFar]} />}
      <hemisphereLight args={[sky.sky, colour(GROUND), 0.5 + sky.daylight * 0.45]} />
      <ambientLight intensity={sky.ambient} />
      <directionalLight
        position={[cx + span * 0.4, span * 0.75, cz - span * 0.35]}
        intensity={sky.sunIntensity}
        color={sky.sun}
        castShadow={shadows}
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-span * 0.6}
        shadow-camera-right={span * 0.6}
        shadow-camera-top={span * 0.6}
        shadow-camera-bottom={-span * 0.6}
        shadow-camera-far={span * 2.2}
      />
    </>
  );
}
