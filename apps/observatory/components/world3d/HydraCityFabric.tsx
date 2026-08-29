"use client";

import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import * as C from "@/lib/city/palette";
import type { BuildingView, CityLive, CityModel } from "@/lib/city/state";

interface Props {
  model: CityModel;
  live: CityLive | null;
  hour: number;
  quality: "low" | "high";
}

const transform = new THREE.Object3D();
const colour = new THREE.Color();
const DISTRICT_ACCENTS = [
  0x39e6ff,
  0xb44dff,
  0x00f0c8,
  0xffc247,
  0xff4d7d,
  0x7f8cff,
  0x5de06f,
  0xf47cff
];

function rectMatrix(
  x: number,
  y: number,
  z: number,
  width: number,
  height: number,
  depth: number,
  angle: number
): THREE.Matrix4 {
  transform.position.set(x, y, z);
  transform.rotation.set(0, -angle, 0);
  transform.scale.set(width, height, depth);
  transform.updateMatrix();
  return transform.matrix;
}

function segmentMatrix(
  ax: number,
  az: number,
  bx: number,
  bz: number,
  y: number,
  height: number,
  width: number
): THREE.Matrix4 {
  const dx = bx - ax;
  const dz = bz - az;
  const length = Math.max(0.5, Math.hypot(dx, dz));
  return rectMatrix(
    (ax + bx) * 0.5,
    y,
    (az + bz) * 0.5,
    length,
    height,
    width,
    Math.atan2(dz, dx)
  );
}

function polygonShape(flat: number[]): THREE.Shape {
  const shape = new THREE.Shape();
  if (flat.length < 6) return shape;
  // ShapeGeometry lives in XY. Negating the source Y lets a -90° X rotation
  // restore the projection's Y axis as Three's positive Z axis.
  shape.moveTo(flat[0], -flat[1]);
  for (let i = 2; i < flat.length; i += 2) shape.lineTo(flat[i], -flat[i + 1]);
  shape.closePath();
  return shape;
}

function DistrictTerrain({ model }: { model: CityModel }) {
  const districtShapes = useMemo(
    () => model.wire.districts.map((district) => ({
      district,
      municipal: polygonShape(district.polygon),
      built: polygonShape(district.built)
    })),
    [model]
  );

  return (
    <group>
      {districtShapes.map(({ district, municipal, built }, index) => (
        <group key={district.id}>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.22, 0]} receiveShadow>
            <shapeGeometry args={[municipal]} />
            <meshStandardMaterial
              color={C.DISTRICT_FILL[district.kind] ?? C.DISTRICT_FILL.mixed}
              roughness={0.98}
              metalness={0.02}
              side={THREE.DoubleSide}
            />
          </mesh>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.12, 0]} receiveShadow>
            <shapeGeometry args={[built]} />
            <meshStandardMaterial
              color={C.BUILT_FILL}
              emissive={DISTRICT_ACCENTS[index % DISTRICT_ACCENTS.length]}
              emissiveIntensity={0.015}
              roughness={0.92}
              metalness={0.08}
              side={THREE.DoubleSide}
            />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function DistrictEdges({ model }: { model: CityModel }) {
  const edges = useMemo(() => {
    const output: Array<[number, number, number, number, number]> = [];
    model.wire.districts.forEach((district, districtIndex) => {
      const points = district.polygon;
      const count = points.length / 2;
      for (let i = 0; i < count; i += 1) {
        const next = (i + 1) % count;
        output.push([
          points[i * 2],
          points[i * 2 + 1],
          points[next * 2],
          points[next * 2 + 1],
          districtIndex
        ]);
      }
    });
    return output;
  }, [model]);
  const ref = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    edges.forEach(([ax, az, bx, bz, district], index) => {
      mesh.setMatrixAt(index, segmentMatrix(ax, az, bx, bz, 0.02, 0.12, 1.4));
      mesh.setColorAt(index, colour.setHex(DISTRICT_ACCENTS[district % DISTRICT_ACCENTS.length]));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [edges]);

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, edges.length]}>
      <boxGeometry args={[1, 1, 1]} />
      <meshBasicMaterial vertexColors transparent opacity={0.34} depthWrite={false} />
    </instancedMesh>
  );
}

function Parcels({ model }: { model: CityModel }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const { rect, use, district, uses } = model.wire.parcels;
  const count = Math.floor(rect.length / 5);

  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    for (let index = 0; index < count; index += 1) {
      const offset = index * 5;
      const parcelUse = uses[use[index]] ?? "vacant";
      const base = C.LAND_USE[parcelUse] ?? C.LAND_USE.vacant;
      mesh.setMatrixAt(index, rectMatrix(
        rect[offset],
        -0.025,
        rect[offset + 1],
        Math.max(1, rect[offset + 2]),
        0.08,
        Math.max(1, rect[offset + 3]),
        rect[offset + 4]
      ));
      colour.setHex(base);
      if (parcelUse === "building") {
        const accent = DISTRICT_ACCENTS[Math.max(0, district[index]) % DISTRICT_ACCENTS.length];
        colour.lerp(new THREE.Color(accent), 0.045);
      }
      mesh.setColorAt(index, colour);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [count, district, rect, use, uses]);

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, count]} receiveShadow>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial vertexColors roughness={0.94} metalness={0.04} />
    </instancedMesh>
  );
}

function Roads({ model }: { model: CityModel }) {
  const shoulders = useRef<THREE.InstancedMesh>(null);
  const surfaces = useRef<THREE.InstancedMesh>(null);
  const markedSegments = useMemo(() => {
    const result: number[] = [];
    for (let i = 0; i < model.segmentCount; i += 1) {
      if (model.streetKlass[i] <= 1 && model.streetWidth[i] >= 7) result.push(i);
    }
    return result;
  }, [model]);
  const markings = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    const shoulderMesh = shoulders.current;
    const surfaceMesh = surfaces.current;
    const markingMesh = markings.current;
    if (!shoulderMesh || !surfaceMesh || !markingMesh) return;

    for (let i = 0; i < model.segmentCount; i += 1) {
      const offset = i * 4;
      const [ax, az, bx, bz] = [
        model.streetLines[offset],
        model.streetLines[offset + 1],
        model.streetLines[offset + 2],
        model.streetLines[offset + 3]
      ];
      shoulderMesh.setMatrixAt(i, segmentMatrix(ax, az, bx, bz, 0.04, 0.13, model.streetWidth[i] + 4.2));
      surfaceMesh.setMatrixAt(i, segmentMatrix(ax, az, bx, bz, 0.12, 0.12, Math.max(3, model.streetWidth[i])));
      const klass = model.wire.streets.klasses[model.streetKlass[i]] ?? "local";
      surfaceMesh.setColorAt(i, colour.setHex(C.STREET_COLOUR[klass] ?? C.STREET_COLOUR.local));
    }

    markedSegments.forEach((segment, index) => {
      const offset = segment * 4;
      markingMesh.setMatrixAt(index, segmentMatrix(
        model.streetLines[offset],
        model.streetLines[offset + 1],
        model.streetLines[offset + 2],
        model.streetLines[offset + 3],
        0.205,
        0.035,
        model.streetKlass[segment] === 0 ? 0.42 : 0.26
      ));
      markingMesh.setColorAt(index, colour.set(model.streetKlass[segment] === 0 ? "#f1c75b" : "#8aa6bc"));
    });

    shoulderMesh.instanceMatrix.needsUpdate = true;
    surfaceMesh.instanceMatrix.needsUpdate = true;
    markingMesh.instanceMatrix.needsUpdate = true;
    if (surfaceMesh.instanceColor) surfaceMesh.instanceColor.needsUpdate = true;
    if (markingMesh.instanceColor) markingMesh.instanceColor.needsUpdate = true;
  }, [markedSegments, model]);

  return (
    <group>
      <instancedMesh ref={shoulders} args={[undefined, undefined, model.segmentCount]} receiveShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#1a202a" roughness={0.88} metalness={0.12} />
      </instancedMesh>
      <instancedMesh ref={surfaces} args={[undefined, undefined, model.segmentCount]} receiveShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial vertexColors roughness={0.72} metalness={0.24} />
      </instancedMesh>
      <instancedMesh ref={markings} args={[undefined, undefined, markedSegments.length]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial vertexColors transparent opacity={0.66} />
      </instancedMesh>
    </group>
  );
}

function Transit({ model }: { model: CityModel }) {
  const lineObjects = useMemo(
    () => model.wire.transit.lines.map((line) => {
      const points: THREE.Vector3[] = [];
      for (let i = 0; i < line.path.length; i += 2) points.push(new THREE.Vector3(line.path[i], 0.31, line.path[i + 1]));
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const material = new THREE.LineBasicMaterial({
        color: line.colour || "#4bd6ff",
        transparent: true,
        opacity: 0.72,
        toneMapped: false
      });
      return { id: line.id, object: new THREE.Line(geometry, material) };
    }),
    [model]
  );
  const stops = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    const mesh = stops.current;
    if (!mesh) return;
    model.wire.transit.stops.forEach((stop, index) => {
      transform.position.set(stop.point[0], 0.7, stop.point[1]);
      transform.rotation.set(0, 0, 0);
      transform.scale.set(1.4, 1.4, 1.4);
      transform.updateMatrix();
      mesh.setMatrixAt(index, transform.matrix);
      mesh.setColorAt(index, colour.setHex(DISTRICT_ACCENTS[Math.max(0, stop.district) % DISTRICT_ACCENTS.length]));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [model]);

  return (
    <group>
      {lineObjects.map(({ id, object }) => <primitive key={id} object={object} />)}
      <instancedMesh ref={stops} args={[undefined, undefined, model.wire.transit.stops.length]}>
        <cylinderGeometry args={[0.55, 0.55, 1, 8]} />
        <meshBasicMaterial vertexColors />
      </instancedMesh>
    </group>
  );
}

function buildingNightLight(hour: number): number {
  if (hour >= 20 || hour < 5) return 1;
  if (hour >= 18) return (hour - 18) * 0.5;
  if (hour < 7) return (7 - hour) * 0.5;
  return 0.08;
}

function Buildings({ model, live, hour }: { model: CityModel; live: CityLive | null; hour: number }) {
  const podiums = useRef<THREE.InstancedMesh>(null);
  const bodies = useRef<THREE.InstancedMesh>(null);
  const roofs = useRef<THREE.InstancedMesh>(null);
  const windows = useRef<THREE.InstancedMesh>(null);
  const windowCount = model.buildings.length * 4;

  useLayoutEffect(() => {
    const podiumMesh = podiums.current;
    const bodyMesh = bodies.current;
    const roofMesh = roofs.current;
    const windowMesh = windows.current;
    if (!podiumMesh || !bodyMesh || !roofMesh || !windowMesh) return;
    const night = buildingNightLight(hour);

    model.buildings.forEach((building, index) => {
      const height = Math.max(2.5, building.height);
      const condition = live?.condition[index] ?? 1;
      const base = C.buildingColour(building.kind);

      podiumMesh.setMatrixAt(index, rectMatrix(
        building.x,
        0.32,
        building.y,
        building.width * 1.08,
        0.55,
        building.depth * 1.08,
        building.angle
      ));
      bodyMesh.setMatrixAt(index, rectMatrix(
        building.x,
        height * 0.5 + 0.58,
        building.y,
        building.width,
        height,
        building.depth,
        building.angle
      ));
      roofMesh.setMatrixAt(index, rectMatrix(
        building.x,
        height + 0.78,
        building.y,
        building.width * 0.92,
        0.34,
        building.depth * 0.92,
        building.angle
      ));

      const bodyColour = colour.setHex(base).multiplyScalar(0.62 + condition * 0.32);
      bodyMesh.setColorAt(index, bodyColour);
      podiumMesh.setColorAt(index, colour.setHex(base).multiplyScalar(0.34));
      roofMesh.setColorAt(index, colour.setHex(base).offsetHSL(0, -0.08, 0.09));

      const c = Math.cos(building.angle);
      const s = Math.sin(building.angle);
      const facadeY = Math.max(2.2, height * 0.58);
      const stripHeight = Math.max(0.8, height * 0.48);
      const frontOffsetX = -s * (building.depth * 0.505);
      const frontOffsetZ = c * (building.depth * 0.505);
      const sideOffsetX = c * (building.width * 0.505);
      const sideOffsetZ = s * (building.width * 0.505);
      const windowBase = index * 4;
      windowMesh.setMatrixAt(windowBase, rectMatrix(
        building.x + frontOffsetX,
        facadeY,
        building.y + frontOffsetZ,
        Math.max(1.2, building.width * 0.54),
        stripHeight,
        0.12,
        building.angle
      ));
      windowMesh.setMatrixAt(windowBase + 1, rectMatrix(
        building.x - frontOffsetX,
        facadeY,
        building.y - frontOffsetZ,
        Math.max(1.2, building.width * 0.54),
        stripHeight,
        0.12,
        building.angle
      ));
      windowMesh.setMatrixAt(windowBase + 2, rectMatrix(
        building.x + sideOffsetX,
        facadeY,
        building.y + sideOffsetZ,
        0.12,
        stripHeight,
        Math.max(1.2, building.depth * 0.48),
        building.angle
      ));
      windowMesh.setMatrixAt(windowBase + 3, rectMatrix(
        building.x - sideOffsetX,
        facadeY,
        building.y - sideOffsetZ,
        0.12,
        stripHeight,
        Math.max(1.2, building.depth * 0.48),
        building.angle
      ));

      const powered = live?.power[building.district] ?? 1;
      const occupied = (live?.occupancy[index] ?? 0) > 0 ? 1 : 0.28;
      const windowColour = colour.set(building.kind === "power_plant" ? "#ffb82e" : "#8be7ff")
        .multiplyScalar(0.18 + night * powered * occupied * 0.9);
      for (let face = 0; face < 4; face += 1) windowMesh.setColorAt(windowBase + face, windowColour);
    });

    for (const mesh of [podiumMesh, bodyMesh, roofMesh, windowMesh]) {
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
  }, [hour, live, live?.tick, model]);

  return (
    <group>
      <instancedMesh ref={podiums} args={[undefined, undefined, model.buildings.length]} receiveShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial vertexColors roughness={0.74} metalness={0.3} />
      </instancedMesh>
      <instancedMesh ref={bodies} args={[undefined, undefined, model.buildings.length]} castShadow receiveShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial vertexColors roughness={0.48} metalness={0.34} />
      </instancedMesh>
      <instancedMesh ref={roofs} args={[undefined, undefined, model.buildings.length]} castShadow>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial vertexColors roughness={0.36} metalness={0.48} />
      </instancedMesh>
      <instancedMesh ref={windows} args={[undefined, undefined, windowCount]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial vertexColors transparent opacity={0.84} toneMapped={false} />
      </instancedMesh>
    </group>
  );
}

function isLandmark(building: BuildingView): boolean {
  return [
    "city_hall",
    "hospital",
    "university",
    "power_plant",
    "water_plant",
    "data_centre",
    "transport_hub",
    "culture"
  ].includes(building.kind);
}

function Landmarks({ model }: { model: CityModel }) {
  const landmarks = useMemo(() => model.buildings.filter(isLandmark), [model]);
  return (
    <group>
      {landmarks.map((building) => {
        const accent = DISTRICT_ACCENTS[Math.max(0, building.district) % DISTRICT_ACCENTS.length];
        const mastHeight = Math.max(7, Math.min(24, building.height * 0.46));
        return (
          <group key={`landmark:${building.id}`} position={[building.x, building.height + 1, building.y]}>
            <mesh position={[0, mastHeight * 0.5, 0]}>
              <cylinderGeometry args={[0.13, 0.38, mastHeight, 8]} />
              <meshStandardMaterial color="#263546" emissive={accent} emissiveIntensity={0.6} metalness={0.72} roughness={0.24} />
            </mesh>
            <mesh position={[0, mastHeight, 0]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[1.5, 0.18, 6, 24]} />
              <meshBasicMaterial color={accent} toneMapped={false} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

function StreetLights({ model, quality }: { model: CityModel; quality: "low" | "high" }) {
  const lights = useMemo(() => {
    const result: Array<[number, number, number]> = [];
    for (let i = 0; i < model.segmentCount; i += quality === "high" ? 1 : 2) {
      if (model.streetKlass[i] > 1) continue;
      const offset = i * 4;
      const ax = model.streetLines[offset];
      const az = model.streetLines[offset + 1];
      const bx = model.streetLines[offset + 2];
      const bz = model.streetLines[offset + 3];
      const dx = bx - ax;
      const dz = bz - az;
      const length = Math.max(1, Math.hypot(dx, dz));
      const nx = -dz / length;
      const nz = dx / length;
      const side = model.streetWidth[i] * 0.5 + 2.3;
      result.push([(ax + bx) * 0.5 + nx * side, (az + bz) * 0.5 + nz * side, i]);
    }
    return result;
  }, [model, quality]);
  const poles = useRef<THREE.InstancedMesh>(null);
  const lamps = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    const poleMesh = poles.current;
    const lampMesh = lamps.current;
    if (!poleMesh || !lampMesh) return;
    lights.forEach(([x, z, segment], index) => {
      transform.position.set(x, 3.2, z);
      transform.rotation.set(0, 0, 0);
      transform.scale.set(0.22, 6.4, 0.22);
      transform.updateMatrix();
      poleMesh.setMatrixAt(index, transform.matrix);
      transform.position.set(x, 6.55, z);
      transform.scale.set(0.72, 0.72, 0.72);
      transform.updateMatrix();
      lampMesh.setMatrixAt(index, transform.matrix);
      lampMesh.setColorAt(index, colour.set(model.streetKlass[segment] === 0 ? "#ffd66b" : "#64dfff"));
    });
    poleMesh.instanceMatrix.needsUpdate = true;
    lampMesh.instanceMatrix.needsUpdate = true;
    if (lampMesh.instanceColor) lampMesh.instanceColor.needsUpdate = true;
  }, [lights, model]);

  return (
    <group>
      <instancedMesh ref={poles} args={[undefined, undefined, lights.length]}>
        <cylinderGeometry args={[1, 1, 1, 6]} />
        <meshStandardMaterial color="#243444" roughness={0.4} metalness={0.72} />
      </instancedMesh>
      <instancedMesh ref={lamps} args={[undefined, undefined, lights.length]}>
        <sphereGeometry args={[1, 7, 5]} />
        <meshBasicMaterial vertexColors toneMapped={false} />
      </instancedMesh>
    </group>
  );
}

function DistrictBeacons({ model }: { model: CityModel }) {
  return (
    <group>
      {model.wire.districts.map((district, index) => {
        const accent = DISTRICT_ACCENTS[index % DISTRICT_ACCENTS.length];
        return (
          <group key={`district-beacon:${district.id}`} position={[district.centre[0], 0.25, district.centre[1]]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[district.block_m * 0.28, district.block_m * 0.3, 48]} />
              <meshBasicMaterial color={accent} transparent opacity={0.26} depthWrite={false} />
            </mesh>
            <mesh position={[0, 13, 0]}>
              <cylinderGeometry args={[0.18, 0.8, 26, 10]} />
              <meshBasicMaterial color={accent} transparent opacity={0.2} depthWrite={false} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

export default function HydraCityFabric({ model, live, hour, quality }: Props) {
  return (
    <group>
      <DistrictTerrain model={model} />
      <DistrictEdges model={model} />
      <Parcels model={model} />
      <Roads model={model} />
      <Transit model={model} />
      <Buildings model={model} live={live} hour={hour} />
      <Landmarks model={model} />
      <StreetLights model={model} quality={quality} />
      <DistrictBeacons model={model} />
    </group>
  );
}
