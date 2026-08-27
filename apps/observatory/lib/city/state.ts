/**
 * The client's picture of the city.
 *
 * `CityModel` decodes the projection once into typed arrays the renderer can walk without
 * allocating, and `CityLive` folds keyframes and deltas into the current state of everyone
 * and everything. Neither of them decides anything about the world: they hold what the
 * server sent, in the shape the renderer wants to read it.
 *
 * Typed arrays matter here. Five thousand agents redrawn sixty times a second is three
 * hundred thousand reads a second; doing that through objects and property lookups is how a
 * city view ends up at fifteen frames.
 */

import { ACTIVITY, SOURCE, type FrameWire, type ProjectionWire, type Vec2 } from "./types";

export interface BuildingView {
  index: number;
  id: string;
  kind: string;
  /** Centre in world metres. */
  x: number;
  y: number;
  width: number;
  depth: number;
  angle: number;
  floors: number;
  height: number;
  district: number;
  address: string;
  entrance: Vec2;
}

/** The projection, decoded once. Immutable for the life of a world. */
export class CityModel {
  readonly wire: ProjectionWire;
  readonly buildings: BuildingView[] = [];
  readonly buildingIndexById = new Map<string, number>();
  readonly districtIndexById = new Map<string, number>();
  /** Street segment endpoints, pre-resolved: [ax, ay, bx, by] per segment. */
  readonly streetLines: Float64Array;
  readonly streetWidth: Float32Array;
  readonly streetKlass: Uint8Array;

  constructor(wire: ProjectionWire) {
    this.wire = wire;

    const b = wire.buildings;
    const count = wire.order.buildings.length;
    for (let i = 0; i < count; i += 1) {
      const o = i * 5;
      const id = wire.order.buildings[i];
      this.buildingIndexById.set(id, i);
      this.buildings.push({
        index: i,
        id,
        kind: b.kind[i],
        x: b.rect[o],
        y: b.rect[o + 1],
        width: b.rect[o + 2],
        depth: b.rect[o + 3],
        angle: b.rect[o + 4],
        floors: b.floors[i],
        height: b.height[i],
        district: b.district[i],
        address: b.address[i],
        entrance: [b.entrance[i * 2], b.entrance[i * 2 + 1]]
      });
    }
    wire.order.districts.forEach((id, i) => this.districtIndexById.set(id, i));

    const segments = wire.streets.a.length;
    this.streetLines = new Float64Array(segments * 4);
    this.streetWidth = new Float32Array(segments);
    this.streetKlass = new Uint8Array(segments);
    for (let i = 0; i < segments; i += 1) {
      const a = wire.streets.a[i] * 2;
      const bIdx = wire.streets.b[i] * 2;
      this.streetLines[i * 4] = wire.streets.nodes[a];
      this.streetLines[i * 4 + 1] = wire.streets.nodes[a + 1];
      this.streetLines[i * 4 + 2] = wire.streets.nodes[bIdx];
      this.streetLines[i * 4 + 3] = wire.streets.nodes[bIdx + 1];
      this.streetWidth[i] = wire.streets.width[i];
      this.streetKlass[i] = wire.streets.klass[i];
    }
  }

  get segmentCount(): number {
    return this.streetWidth.length;
  }

  streetName(segment: number): string {
    const index = this.wire.streets.name[segment];
    return index >= 0 ? this.wire.street_names[index] : "";
  }

  building(id: string): BuildingView | null {
    const index = this.buildingIndexById.get(id);
    return index === undefined ? null : this.buildings[index];
  }
}

/**
 * The living city: who is where, right now, and how sure we are.
 *
 * Agent rows are held in parallel typed arrays indexed by *slot*. Slots are append-only, so
 * a person keeps theirs for as long as they live and the renderer's sprite for that slot
 * never has to be rebuilt. Slots of the dead are freed and reused.
 */
export class CityLive {
  tick = -1;
  simTime = "";
  timelineId = "";
  cohortPopulation = 0;
  presence = { observed: 0, derived: 0, unknown: 0, observed_share: 0 };

  /** person id -> slot */
  readonly slotOf = new Map<string, number>();
  readonly idOf: string[] = [];
  building: Int32Array;
  source: Uint8Array;
  activity: Uint8Array;
  tier: Uint8Array;
  live: Uint8Array;
  /** Where this person was before their last move, and when the move began. */
  fromBuilding: Int32Array;
  movedAt: Float64Array;
  private free: number[] = [];
  private capacity: number;
  count = 0;

  /** Per-building dynamic state, indexed the same way as the projection's buildings. */
  occupancy: Int32Array;
  awake: Int32Array;
  condition: Float32Array;

  /** Per-district dynamic state. */
  population: Int32Array;
  asleepShare: Float32Array;
  unrest: Float32Array;
  power: Float32Array;

  constructor(buildingCount: number, districtCount: number, capacity = 8192) {
    this.capacity = capacity;
    this.building = new Int32Array(capacity).fill(-1);
    this.source = new Uint8Array(capacity);
    this.activity = new Uint8Array(capacity);
    this.tier = new Uint8Array(capacity);
    this.live = new Uint8Array(capacity);
    this.fromBuilding = new Int32Array(capacity).fill(-1);
    this.movedAt = new Float64Array(capacity);

    this.occupancy = new Int32Array(buildingCount);
    this.awake = new Int32Array(buildingCount);
    this.condition = new Float32Array(buildingCount).fill(1);
    this.population = new Int32Array(districtCount);
    this.asleepShare = new Float32Array(districtCount);
    this.unrest = new Float32Array(districtCount);
    this.power = new Float32Array(districtCount).fill(1);
  }

  apply(frame: FrameWire): void {
    if (frame.kind === "keyframe") this.reset();

    // The world publishes positions on its own cadence, so a person changing building
    // arrives as a jump. Remembering where they were, and when, is what lets the renderer
    // walk them there instead -- the difference between a city and a slideshow.
    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    const { id, b, s, a, t } = frame.agents;
    for (let i = 0; i < id.length; i += 1) {
      const slot = this.slotFor(id[i]);
      const was = this.building[slot];
      if (was >= 0 && b[i] >= 0 && was !== b[i]) {
        this.fromBuilding[slot] = was;
        this.movedAt[slot] = now;
      }
      this.building[slot] = b[i];
      this.source[slot] = s[i];
      this.activity[slot] = a[i];
      this.tier[slot] = t[i];
    }
    for (const gone of frame.gone) this.release(gone);

    const bw = frame.buildings;
    for (let i = 0; i < bw.i.length; i += 1) {
      const index = bw.i[i];
      if (index >= this.occupancy.length) continue;
      this.occupancy[index] = bw.occupancy[i];
      this.awake[index] = bw.awake[i];
      this.condition[index] = bw.condition[i] / 1000;
    }

    const dw = frame.districts;
    for (let i = 0; i < dw.i.length; i += 1) {
      const index = dw.i[i];
      if (index >= this.population.length) continue;
      this.population[index] = dw.population[i];
      this.asleepShare[index] = dw.asleep[i] / 1000;
      this.unrest[index] = dw.unrest[i] / 1000;
      this.power[index] = dw.power[i] / 1000;
    }

    this.tick = frame.tick;
    this.simTime = frame.sim_time;
    this.timelineId = frame.timeline_id;
    this.presence = frame.presence;
    this.cohortPopulation = frame.cohort_population;
  }

  private reset(): void {
    this.slotOf.clear();
    this.idOf.length = 0;
    this.live.fill(0);
    this.building.fill(-1);
    this.fromBuilding.fill(-1);
    this.free = [];
    this.count = 0;
  }

  private slotFor(personId: string): number {
    const existing = this.slotOf.get(personId);
    if (existing !== undefined) return existing;

    let slot: number;
    if (this.free.length) {
      slot = this.free.pop() as number;
    } else {
      slot = this.count;
      if (slot >= this.capacity) this.grow();
    }
    this.slotOf.set(personId, slot);
    this.idOf[slot] = personId;
    this.live[slot] = 1;
    this.count = Math.max(this.count, slot + 1);
    return slot;
  }

  private release(personId: string): void {
    const slot = this.slotOf.get(personId);
    if (slot === undefined) return;
    this.slotOf.delete(personId);
    this.live[slot] = 0;
    this.building[slot] = -1;
    this.free.push(slot);
  }

  private grow(): void {
    const next = this.capacity * 2;
    const building = new Int32Array(next).fill(-1);
    building.set(this.building);
    const source = new Uint8Array(next);
    source.set(this.source);
    const activity = new Uint8Array(next);
    activity.set(this.activity);
    const tier = new Uint8Array(next);
    tier.set(this.tier);
    const live = new Uint8Array(next);
    live.set(this.live);
    const fromBuilding = new Int32Array(next).fill(-1);
    fromBuilding.set(this.fromBuilding);
    const movedAt = new Float64Array(next);
    movedAt.set(this.movedAt);

    this.fromBuilding = fromBuilding;
    this.movedAt = movedAt;
    this.building = building;
    this.source = source;
    this.activity = activity;
    this.tier = tier;
    this.live = live;
    this.capacity = next;
  }

  isAsleep(slot: number): boolean {
    const value = this.activity[slot];
    return value === ACTIVITY.SLEEP || value === ACTIVITY.DORMANT;
  }

  isDerived(slot: number): boolean {
    return this.source[slot] === SOURCE.DERIVED;
  }

  /** 0 while a person is still at their old address, 1 once they have arrived. */
  travel(slot: number, now: number, durationMs: number): number {
    if (this.fromBuilding[slot] < 0) return 1;
    const t = (now - this.movedAt[slot]) / durationMs;
    if (t >= 1) {
      this.fromBuilding[slot] = -1;
      return 1;
    }
    return t < 0 ? 0 : t;
  }

  slotFromId(personId: string): number | undefined {
    return this.slotOf.get(personId);
  }
}

/** The simulated hour, parsed from the clock label the server sends ("Y0-M01-D01 14:30"). */
export function hourOf(simTime: string): number {
  const match = /(\d{2}):(\d{2})$/.exec(simTime);
  if (!match) return 12;
  return Number(match[1]) + Number(match[2]) / 60;
}
