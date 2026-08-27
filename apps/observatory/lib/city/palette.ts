/**
 * Every colour the city uses, and the reasoning behind the ones that matter.
 *
 * The brief asked for dark and cyberpunk, and then said the thing that actually governs
 * this file: *readability of the simulation beats effects*. So the palette is dark and
 * saturated, but the saturation is spent on information -- what a building is for, whether
 * a person is awake, whether we know where they are -- and never on decoration that would
 * compete with it.
 *
 * Two rules are load-bearing:
 *
 * 1. **Derived positions look derived.** A person whose position the view inferred is drawn
 *    dimmer and smaller than one the world actually placed. A viewer should be able to see
 *    the difference without opening a panel.
 * 2. **Cohorts never look like people.** The 45,000 residents carried as statistics are
 *    drawn, if at all, as diffuse density -- never as dots that could be mistaken for
 *    someone you could click and follow.
 */

export const GROUND = 0x080910;
export const WATER = 0x0b1a26;
export const OUTSIDE = 0x06070b;

export const DISTRICT_FILL: Record<string, number> = {
  commercial: 0x1a2133,
  elite: 0x1c2330,
  mixed: 0x192030,
  residential: 0x171e2c,
  industrial: 0x1f1f2a,
  port: 0x152029,
  periphery: 0x161b25
};

export const DISTRICT_EDGE = 0x39435a;
export const BUILT_FILL = 0x0d121b;

export const STREET_COLOUR: Record<string, number> = {
  arterial: 0x4b5672,
  collector: 0x3e4762,
  local: 0x333b52
};

export const LAND_USE: Record<string, number> = {
  building: 0x000000,
  park: 0x16301f,
  plaza: 0x2a2733,
  yard: 0x242430,
  water: WATER,
  vacant: 0x11151c
};

/** Building colour by what it is for. Civic and industrial read distinctly at a glance. */
export const BUILDING_KIND: Record<string, number> = {
  housing: 0x5d6d9a,
  retail: 0xc96f4a,
  office: 0x7f8ec4,
  factory: 0x8a6a4a,
  school: 0x57a37a,
  university: 0x4d9d95,
  hospital: 0xc05a6e,
  police: 0x4a6fa5,
  court: 0x8a7fb5,
  city_hall: 0xb59a4a,
  power_plant: 0xc7a83c,
  water_plant: 0x4aa5b5,
  data_centre: 0x6ab5c7,
  transport_hub: 0xb5764a,
  culture: 0xa55fa5
};

export const BUILDING_DEFAULT = 0x53617f;

/** Agents. Awake is warm and bright; asleep is cold and dim. */
export const AGENT_AWAKE = 0xffd479;
export const AGENT_IDLE = 0xd9a15c;
export const AGENT_ASLEEP = 0x4a6a9c;
export const AGENT_DORMANT = 0x35455f;
export const AGENT_PERSISTENT = 0xff5cc8;
export const AGENT_FOLLOWED = 0x4bd6ff;

/** Ambient crowd density from cohorts. Never a dot, never clickable. */
export const COHORT_HAZE = 0x2d3a5c;

export const EVENT_PULSE = 0xff5cc8;
export const SELECTION = 0x4bd6ff;

/** Sequential ramp for a layer where high is good, and one where high is bad. */
const GOOD_RAMP = [0x14202f, 0x1a3c46, 0x246154, 0x468c54, 0x8fae4e];
const BAD_RAMP = [0x14202f, 0x3a2f4a, 0x6b3352, 0x9c4149, 0xc87c3a];

export function rampColour(value: number, highIsBad: boolean): number {
  const ramp = highIsBad ? BAD_RAMP : GOOD_RAMP;
  const t = Math.max(0, Math.min(1, value)) * (ramp.length - 1);
  const i = Math.floor(t);
  if (i >= ramp.length - 1) return ramp[ramp.length - 1];
  return mix(ramp[i], ramp[i + 1], t - i);
}

export function mix(a: number, b: number, t: number): number {
  const ar = (a >> 16) & 0xff;
  const ag = (a >> 8) & 0xff;
  const ab = a & 0xff;
  const br = (b >> 16) & 0xff;
  const bg = (b >> 8) & 0xff;
  const bb = b & 0xff;
  return (
    ((ar + (br - ar) * t) << 16) |
    (((ag + (bg - ag) * t) | 0) << 8) |
    ((ab + (bb - ab) * t) | 0)
  );
}

export function buildingColour(kind: string): number {
  return BUILDING_KIND[kind] ?? BUILDING_DEFAULT;
}

/**
 * Night falls on the whole city at once, so buildings darken and lit windows show.
 * The hour comes from the simulated clock, never from the viewer's own clock.
 */
export function daylight(hour: number): number {
  if (hour >= 8 && hour < 17) return 1;
  if (hour >= 6 && hour < 8) return 0.55 + (hour - 6) * 0.22;
  if (hour >= 17 && hour < 20) return 1 - (hour - 17) * 0.24;
  return 0.28;
}
