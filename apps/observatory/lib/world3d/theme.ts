/**
 * The look of Hydra in three dimensions.
 *
 * The 2D City View already has a palette, and this file does not invent a second one: it
 * lifts `lib/city/palette.ts` into three.js colours and adds only what a lit scene needs and
 * a flat one does not — how bright the sun is at a given simulated hour, how far the fog
 * reaches, how a cube should glow once its windows are on.
 *
 * The governing rule is the same one the 2D palette states: **readability of the simulation
 * beats effects**. A viewer must be able to look at the city for three seconds and say what
 * that block is for. So zoning carries the saturation, the ground stays dark, and the
 * atmosphere is only ever allowed to tint — never to hide.
 */

import * as THREE from "three";

import {
  BUILDING_DEFAULT,
  BUILDING_KIND,
  DISTRICT_FILL,
  LAND_USE,
  STREET_COLOUR,
  mix
} from "@/lib/city/palette";

/** A three.js colour from one of the palette's 0xRRGGBB numbers. Cached: colours are hot. */
const colourCache = new Map<number, THREE.Color>();
export function colour(value: number): THREE.Color {
  let existing = colourCache.get(value);
  if (!existing) {
    existing = new THREE.Color(value);
    colourCache.set(value, existing);
  }
  return existing;
}

/**
 * Zone colour, brightened for a lit scene.
 *
 * The 2D map draws unlit fills, so its building colours are already at their final
 * brightness. Here the same colours pass through a light and lose roughly a third of it,
 * which is enough to turn a legible zoning map into brown soup. Lifting them here — rather
 * than editing the shared palette — keeps the two views recognisably the same city.
 */
export function zoneColour(kind: string): number {
  return brighten(BUILDING_KIND[kind] ?? BUILDING_DEFAULT, 0.34);
}

/**
 * District ground colour.
 *
 * The 2D palette separates districts by a few points of lightness, which is right for a flat
 * map read at close zoom and wrong for a city seen from two kilometres up, where those few
 * points vanish into one grey blob. So the 3D map keeps the palette's hues and spreads them
 * further apart, and adds nothing that is not already a distinction the world makes.
 */
const DISTRICT_LIFT: Record<string, [tint: number, amount: number]> = {
  commercial: [0x4d7cc4, 0.34],
  elite: [0x8f7cc4, 0.32],
  mixed: [0x5f8fa8, 0.28],
  residential: [0x5fa87e, 0.3],
  industrial: [0xc49a5f, 0.28],
  port: [0x4fa8b5, 0.3],
  periphery: [0x6f7a8c, 0.22]
};

export function districtColour(kind: string): number {
  const base = DISTRICT_FILL[kind] ?? DISTRICT_FILL.mixed;
  const [tint, amount] = DISTRICT_LIFT[kind] ?? DISTRICT_LIFT.mixed;
  return brighten(mix(base, tint, amount), 0.16);
}

export function landUseColour(use: string): number {
  return brighten(LAND_USE[use] ?? LAND_USE.vacant, 0.2);
}

export function streetColour(klass: string): number {
  return brighten(STREET_COLOUR[klass] ?? STREET_COLOUR.local, 0.16);
}

export function brighten(value: number, amount: number): number {
  return mix(value, 0xffffff, Math.max(0, Math.min(1, amount)));
}

/** The zoning legend, in the order a viewer should read it. Drives the on-screen key. */
export const ZONE_LEGEND: Array<[kind: string, label: string]> = [
  ["housing", "Housing"],
  ["office", "Office"],
  ["retail", "Retail"],
  ["factory", "Industry"],
  ["power_plant", "Power"],
  ["water_plant", "Water"],
  ["hospital", "Health"],
  ["school", "Education"],
  ["city_hall", "Civic"],
  ["culture", "Culture"],
  ["transport_hub", "Transport"],
  ["data_centre", "Data"]
];

export interface Atmosphere {
  /** 0 at midnight, 1 at midday. */
  daylight: number;
  sky: THREE.Color;
  fog: THREE.Color;
  sun: THREE.Color;
  sunIntensity: number;
  ambient: number;
  /** How strongly lit windows show through the cladding. */
  windowGlow: number;
}

/**
 * The sky at a simulated hour.
 *
 * The hour comes from the world's clock, never the viewer's: two people watching the same
 * timeline from different continents see the same dusk.
 */
export function atmosphere(hour: number): Atmosphere {
  const day = Math.max(0, Math.sin(((hour - 6) / 12) * Math.PI));
  const dusk = Math.max(0, 1 - Math.abs(hour - 18) / 2.4) + Math.max(0, 1 - Math.abs(hour - 6) / 2.4);
  const night = 1 - day;
  // Every colour here is written as an sRGB hex and handed to `new THREE.Color(hex)`, which
  // converts it into the renderer's working space. `setHSL` does not: it takes its value as
  // already-linear, which silently washes a dark sky out into daylight grey. That mistake is
  // easy to make and hard to see, so this file never uses it.
  return {
    daylight: day,
    sky: new THREE.Color(mix(0x060912, 0x1d3352, day)),
    fog: new THREE.Color(mix(0x070a12, 0x223550, day * 0.75)),
    sun: new THREE.Color(mix(mix(0x6f83c4, 0xdce9ff, day), 0xff9d5c, Math.min(0.6, dusk * 0.5))),
    // The night floor is deliberately generous. A real city at 03:00 is nearly black, and a
    // nearly black city is a view a jury learns nothing from: zoning has to stay legible
    // around the clock, so night dims the city rather than switching it off.
    sunIntensity: 0.45 + day * 1.25,
    ambient: 0.34 + day * 0.3,
    windowGlow: Math.min(1, night * 1.15)
  };
}
