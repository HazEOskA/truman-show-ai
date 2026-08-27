/**
 * The city renderer.
 *
 * One decision shapes this whole file. The dimetric projection is *affine* -- screen = M ·
 * world + t for a fixed 2 x 2 matrix M -- which means the entire static city can be built
 * once in world coordinates and then drawn by handing Pixi a matrix each frame, instead of
 * being re-tessellated as the camera moves. Nine hundred street segments, thirteen hundred
 * plots and six hundred buildings become a handful of Graphics objects that are rebuilt only
 * when what they show actually changes.
 *
 * Height rides along in the same trick. A pure vertical screen offset of `h` pixels is the
 * world-space offset `(-h, -h)` under this matrix, so a building's roof is just its footprint
 * translated in world space. No second coordinate system, no per-frame projection maths.
 *
 * What is left to do per frame is only what moves: the agents, and only the ones inside the
 * viewport at a zoom where individuals are worth drawing at all. That is what keeps a city of
 * five thousand people running at sixty frames.
 */

import { Application, Container, Graphics, Matrix, Text, TextStyle } from "pixi.js";

import { Camera, Lod, lodFor } from "./camera";
import * as C from "./palette";
import { CityLive, CityModel, hourOf, type BuildingView } from "./state";
import { ACTIVITY, SOURCE, TIER, type CityEvent, type LayerMeta } from "./types";

export interface PickResult {
  kind: "building" | "district";
  id: string;
  index: number;
}

export interface RendererOptions {
  onPick?: (hit: PickResult | null) => void;
  onCamera?: () => void;
}

interface ActiveLayer {
  meta: LayerMeta;
  values: Record<string, number>;
}

const TAU = Math.PI * 2;

export class CityRenderer {
  readonly camera = new Camera();
  private app: Application | null = null;
  private model: CityModel | null = null;
  private live: CityLive | null = null;

  private world = new Container();
  private ground = new Graphics();
  private structures = new Graphics();
  private crowd = new Graphics();
  private agents = new Graphics();
  private overlay = new Graphics();
  private labels = new Container();

  private layer: ActiveLayer | null = null;
  private events: CityEvent[] = [];
  private selection: PickResult | null = null;
  private followed: string | null = null;
  private showDerived = true;
  private showCohorts = true;

  private groundDirty = true;
  private structuresDirty = true;
  private needsFraming = false;
  private lastLod: Lod = Lod.Region;
  private groundScale = 0;
  private groundLight = -1;
  private options: RendererOptions = {};
  private detached: (() => void)[] = [];
  private frameCount = 0;
  private frameMs = 0;

  async attach(canvas: HTMLCanvasElement, options: RendererOptions = {}): Promise<void> {
    this.options = options;
    const app = new Application();
    await app.init({
      canvas,
      antialias: true,
      background: C.OUTSIDE,
      resolution: Math.min(2, window.devicePixelRatio || 1),
      autoDensity: true,
      preference: "webgl"
    });
    this.app = app;

    this.world.addChild(this.ground, this.structures, this.crowd, this.agents, this.overlay, this.labels);
    app.stage.addChild(this.world);

    // Own the resize rather than using `resizeTo`. Pixi's own handler only follows window
    // resize events, so a canvas that grows because its flex parent laid out -- which is
    // what happens on first paint -- leaves the renderer stuck at its 800x600 default. Every
    // camera decision is made against that size, so getting it wrong mis-frames the city.
    const host = canvas.parentElement ?? canvas;
    const fit = () => {
      const rect = host.getBoundingClientRect();
      const width = Math.max(1, Math.round(rect.width));
      const height = Math.max(1, Math.round(rect.height));
      if (width !== app.renderer.screen.width || height !== app.renderer.screen.height) {
        app.renderer.resize(width, height);
        this.groundDirty = true;
      }
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(host);
    this.detached.push(() => observer.disconnect());

    this.bindInput(canvas);
    app.ticker.add(() => this.draw());
  }

  detach(): void {
    for (const off of this.detached) off();
    this.detached = [];
    this.app?.destroy(true, { children: true });
    this.app = null;
  }

  // -- inputs ---------------------------------------------------------------------

  setModel(model: CityModel): void {
    this.model = model;
    this.groundDirty = true;
    this.structuresDirty = true;
    // Framing needs a viewport, and `attach` is async: the projection often arrives first.
    // Defer to the first draw, which is the earliest moment the canvas has a real size.
    this.needsFraming = true;
  }

  setLive(live: CityLive): void {
    this.live = live;
    this.structuresDirty = true;
  }

  setLayer(layer: ActiveLayer | null): void {
    this.layer = layer;
    this.groundDirty = true;
    this.structuresDirty = true;
  }

  setEvents(events: CityEvent[]): void {
    this.events = events;
  }

  setDerivedVisible(visible: boolean): void {
    this.showDerived = visible;
  }

  setCohortsVisible(visible: boolean): void {
    this.showCohorts = visible;
  }

  follow(personId: string | null): void {
    this.followed = personId;
  }

  select(hit: PickResult | null): void {
    this.selection = hit;
  }

  focusBuilding(id: string): void {
    const building = this.model?.building(id);
    if (building) {
      this.camera.centreOn(building.x, building.y);
      this.camera.zoom = Math.max(this.camera.zoom, 1.6);
      this.options.onCamera?.();
    }
  }

  frameCity(): void {
    if (this.model) this.camera.frame(this.builtBounds(this.model));
    this.options.onCamera?.();
  }

  get stats(): { fps: number; lod: Lod; drawMs: number; width: number; height: number } {
    return {
      fps: this.app ? Math.round(this.app.ticker.FPS) : 0,
      lod: this.lastLod,
      drawMs: Math.round(this.frameMs * 100) / 100,
      width: Math.round(this.camera.width),
      height: Math.round(this.camera.height)
    };
  }

  /** The settled part of the city, which is what a viewer wants framed -- not the fields. */
  private builtBounds(model: CityModel) {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const district of model.wire.districts) {
      const points = district.built.length ? district.built : district.polygon;
      for (let i = 0; i < points.length; i += 2) {
        minX = Math.min(minX, points[i]);
        maxX = Math.max(maxX, points[i]);
        minY = Math.min(minY, points[i + 1]);
        maxY = Math.max(maxY, points[i + 1]);
      }
    }
    if (!Number.isFinite(minX)) return model.wire.bounds;
    return { min_x: minX, min_y: minY, max_x: maxX, max_y: maxY };
  }

  // -- input handling -------------------------------------------------------------

  private bindInput(canvas: HTMLCanvasElement): void {
    let dragging = false;
    let moved = 0;
    let lastX = 0;
    let lastY = 0;

    const down = (e: PointerEvent) => {
      dragging = true;
      moved = 0;
      lastX = e.clientX;
      lastY = e.clientY;
      canvas.setPointerCapture(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (!dragging) return;
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      moved += Math.abs(dx) + Math.abs(dy);
      lastX = e.clientX;
      lastY = e.clientY;
      this.camera.panByScreen(dx, dy);
      this.followed = null;
      this.options.onCamera?.();
    };
    const up = (e: PointerEvent) => {
      if (dragging && moved < 5) {
        const rect = canvas.getBoundingClientRect();
        this.options.onPick?.(this.pick(e.clientX - rect.left, e.clientY - rect.top));
      }
      dragging = false;
      if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
    };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      this.camera.zoomAt(e.clientX - rect.left, e.clientY - rect.top, e.deltaY < 0 ? 1.14 : 1 / 1.14);
      this.options.onCamera?.();
    };

    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("wheel", wheel, { passive: false });

    this.detached.push(() => {
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", up);
      canvas.removeEventListener("wheel", wheel);
    });
  }

  /** What is under a screen point. Buildings first: they are what a viewer aims at. */
  pick(px: number, py: number): PickResult | null {
    if (!this.model) return null;
    const [wx, wy] = this.camera.toWorld(px, py);

    let best: PickResult | null = null;
    let bestDepth = -Infinity;
    for (const building of this.model.buildings) {
      if (building.width <= 0) continue;
      if (Math.abs(wx - building.x) > building.width + building.depth) continue;
      if (Math.abs(wy - building.y) > building.width + building.depth) continue;
      if (!inRect(wx, wy, building)) continue;
      const depth = building.x + building.y;
      if (depth > bestDepth) {
        bestDepth = depth;
        best = { kind: "building", id: building.id, index: building.index };
      }
    }
    if (best) return best;

    for (let i = 0; i < this.model.wire.districts.length; i += 1) {
      if (pointInFlatPolygon(wx, wy, this.model.wire.districts[i].polygon)) {
        return { kind: "district", id: this.model.wire.districts[i].id, index: i };
      }
    }
    return null;
  }

  // -- drawing --------------------------------------------------------------------

  private draw(): void {
    const app = this.app;
    const model = this.model;
    if (!app || !model) return;
    const started = performance.now();

    this.camera.resize({ width: app.renderer.screen.width, height: app.renderer.screen.height });

    if (this.needsFraming && this.camera.width > 2) {
      this.needsFraming = false;
      this.camera.frame(this.builtBounds(model));
      this.options.onCamera?.();
    }

    if (this.followed && this.live) {
      const slot = this.live.slotFromId(this.followed);
      if (slot !== undefined) {
        const index = this.live.building[slot];
        const building = index >= 0 ? model.buildings[index] : null;
        if (building) this.camera.centreOn(building.x, building.y);
      }
    }

    // One matrix, applied to everything static. This is the whole camera.
    const s = this.camera.scale;
    this.world.setFromMatrix(
      new Matrix(
        s,
        s * 0.5,
        -s,
        s * 0.5,
        this.camera.width * 0.5 - (this.camera.x - this.camera.y) * s,
        this.camera.height * 0.5 - (this.camera.x + this.camera.y) * s * 0.5
      )
    );

    const lod = lodFor(this.camera.scale);
    if (lod !== this.lastLod) {
      this.lastLod = lod;
      this.groundDirty = true;
      this.structuresDirty = true;
    }
    // Some ground widths have a floor expressed in screen pixels, so they are only correct
    // for the zoom they were built at. Rebuild when the zoom has drifted far enough to
    // matter -- otherwise a road drawn thick enough to see from orbit stays that thick all
    // the way down to street level.
    const drift = this.groundScale > 0 ? this.camera.scale / this.groundScale : Infinity;
    if (drift < 0.8 || drift > 1.25) this.groundDirty = true;

    // Night has to fall on the whole city, not only on its buildings. A dark skyline over
    // daylit parks reads as a rendering bug, which is worse than either look on its own.
    const light = C.daylight(this.live ? hourOf(this.live.simTime) : 12);
    if (Math.abs(light - this.groundLight) > 0.02) this.groundDirty = true;

    if (this.groundDirty) {
      this.drawGround(model, lod, light);
      this.groundDirty = false;
      this.groundScale = this.camera.scale;
      this.groundLight = light;
    }
    if (this.structuresDirty) {
      this.drawStructures(model, lod);
      this.structuresDirty = false;
    }

    this.drawCrowd(model, lod);
    this.drawAgents(model, lod);
    this.drawOverlay(model, lod);

    this.frameCount += 1;
    this.frameMs = this.frameMs * 0.9 + (performance.now() - started) * 0.1;
  }

  private drawGround(model: CityModel, lod: Lod, light: number): void {
    const g = this.ground;
    g.clear();
    const lit = (colour: number) => mixColour(colour, C.GROUND, (1 - light) * 0.62);

    g.poly(model.wire.boundary).fill({ color: C.GROUND, alpha: 1 });

    // A layer tints the ground; it never replaces it. The base fill and the built fabric
    // stay dark underneath so streets and buildings remain readable with any layer on --
    // a choropleth bright enough to drown the city answers a question nobody asked.
    for (let i = 0; i < model.wire.districts.length; i += 1) {
      const district = model.wire.districts[i];
      g.poly(district.polygon).fill({
        color: lit(C.DISTRICT_FILL[district.kind] ?? C.DISTRICT_FILL.mixed),
        alpha: 1
      });
      const tint = this.districtTint(district.id, district.kind);
      if (this.layer?.meta.scope === "district") {
        g.poly(district.polygon).fill({ color: lit(tint), alpha: 0.5 });
      }
      g.poly(district.polygon).stroke({ width: 2 / this.camera.scale, color: C.DISTRICT_EDGE, alpha: 0.5 });
      if (district.built.length) {
        g.poly(district.built).fill({ color: C.BUILT_FILL, alpha: 0.88 });
      }
    }

    if (lod >= Lod.Quarter) {
      const parcels = model.wire.parcels;
      const uses = parcels.uses;
      for (let i = 0; i < parcels.use.length; i += 1) {
        const use = uses[parcels.use[i]];
        if (use === "building") continue;
        const o = i * 5;
        const colour = lit(C.LAND_USE[use] ?? C.LAND_USE.vacant);
        polyRect(g, parcels.rect[o], parcels.rect[o + 1], parcels.rect[o + 2], parcels.rect[o + 3], parcels.rect[o + 4]);
        g.fill({ color: colour, alpha: use === "vacant" ? 0.5 : 0.85 });
      }
    }

    // Streets. Widths are real metres, so they thin out naturally as the camera pulls back.
    const klasses = model.wire.streets.klasses;
    for (let i = 0; i < model.segmentCount; i += 1) {
      const klass = klasses[model.streetKlass[i]];
      if (lod === Lod.Region && klass === "local") continue;
      if (lod === Lod.Region && klass === "collector") continue;
      const o = i * 4;
      g.moveTo(model.streetLines[o], model.streetLines[o + 1]);
      g.lineTo(model.streetLines[o + 2], model.streetLines[o + 3]);
      g.stroke({
        width: Math.max(model.streetWidth[i], 1.5 / this.camera.scale),
        color: lit(C.STREET_COLOUR[klass] ?? C.STREET_COLOUR.local),
        alpha: 0.95,
        cap: "round"
      });
    }

    // Transit is context, not subject: thin enough to trace, faint enough to ignore.
    for (const line of model.wire.transit.lines) {
      g.poly(line.path, false).stroke({
        width: Math.max(5, 1.5 / this.camera.scale),
        color: Number(`0x${line.colour.slice(1)}`),
        alpha: 0.3
      });
    }
  }

  private drawStructures(model: CityModel, lod: Lod): void {
    const g = this.structures;
    g.clear();
    if (lod === Lod.Region) return;

    const live = this.live;
    const light = C.daylight(live ? hourOf(live.simTime) : 12);

    // Painter's algorithm: far to near along the dimetric depth axis.
    const order = model.buildings
      .filter((b) => b.width > 0)
      .sort((a, b) => a.x + a.y - (b.x + b.y));

    for (const building of order) {
      const tint = this.buildingTint(building);
      const lift = building.height * 0.82;
      const shade = mixColour(tint, C.GROUND, 1 - light * 0.75);

      // Walls: the footprint extruded toward the roof, drawn as two visible faces.
      const corners = rectCorners(building.x, building.y, building.width, building.depth, building.angle);
      const roof = corners.map(([x, y]) => [x - lift, y - lift] as [number, number]);

      for (let i = 0; i < 4; i += 1) {
        const a = corners[i];
        const b = corners[(i + 1) % 4];
        // Only the two faces turned toward the camera are visible in a fixed projection.
        if (a[0] + a[1] + (b[0] + b[1]) < building.x * 2 + building.y * 2) continue;
        const ra = roof[i];
        const rb = roof[(i + 1) % 4];
        g.poly([a[0], a[1], b[0], b[1], rb[0], rb[1], ra[0], ra[1]]).fill({
          color: mixColour(shade, 0x000000, 0.34),
          alpha: 1
        });
      }

      g.poly(roof.flat()).fill({ color: shade, alpha: 1 });
      if (lod >= Lod.Street) {
        g.poly(roof.flat()).stroke({ width: 0.6, color: mixColour(shade, 0x000000, 0.55), alpha: 0.9 });
      }

      // Lit windows: the building is awake because people in it are, not because it is night.
      if (live && lod >= Lod.Street) {
        const awake = live.awake[building.index] ?? 0;
        if (awake > 0 && light < 0.7) {
          const glow = Math.min(1, awake / Math.max(4, building.floors * 6));
          g.poly(roof.flat()).fill({ color: 0xffd479, alpha: 0.05 + glow * 0.22 });
        }
      }
    }
  }

  /**
   * Cohort haze: the residents Hydra carries as statistics.
   *
   * Drawn as a soft density over the district, never as individuals. Forty-five thousand
   * people exist in this city as numbers, and a viewer must never be able to click one and
   * be told a name the simulation never had.
   */
  private drawCrowd(model: CityModel, lod: Lod): void {
    const g = this.crowd;
    g.clear();
    if (!this.showCohorts || !this.live) return;

    for (let i = 0; i < model.wire.districts.length; i += 1) {
      const district = model.wire.districts[i];
      const population = this.live.population[i] ?? 0;
      if (population <= 0) continue;
      const awakeShare = 1 - (this.live.asleepShare[i] ?? 0);
      const points = district.built.length ? district.built : district.polygon;
      const density = Math.min(0.30, population / 40_000);
      g.poly(points).fill({ color: C.COHORT_HAZE, alpha: density * (0.35 + awakeShare * 0.65) });
    }
  }

  private drawAgents(model: CityModel, lod: Lod): void {
    const g = this.agents;
    g.clear();
    const live = this.live;
    if (!live || lod < Lod.Street) return;

    const view = this.camera.visibleBounds(120);
    // Agents live in the world container, so their radius is in metres -- but a person has
    // to stay a couple of pixels wide or they vanish exactly when you zoom out to look for
    // a crowd. Floor the radius in screen space and let it shrink to life size up close.
    // Floored so a person never vanishes, capped so a full building never fuses into one
    // blob. Between those two the dot is roughly two pixels at any zoom.
    const radius = Math.min(5.0, Math.max(lod >= Lod.Close ? 1.7 : 1.4, 2.0 / this.camera.scale));
    const perBuilding = new Map<number, number>();

    for (let slot = 0; slot < live.count; slot += 1) {
      if (!live.live[slot]) continue;
      const index = live.building[slot];
      if (index < 0) continue;
      const building = model.buildings[index];
      if (!building || building.width <= 0) continue;
      if (building.x < view.min_x || building.x > view.max_x) continue;
      if (building.y < view.min_y || building.y > view.max_y) continue;

      const derived = live.source[slot] === SOURCE.DERIVED;
      if (derived && !this.showDerived) continue;

      // Spread the occupants of one building around its entrance so they are countable.
      const nth = perBuilding.get(index) ?? 0;
      perBuilding.set(index, nth + 1);
      const ring = Math.floor(nth / 8);
      const angle = (nth % 8) * (TAU / 8) + ring * 0.4;
      const spread = building.width * 0.4 + ring * radius * 2.3;
      const x = building.entrance[0] + Math.cos(angle) * spread;
      const y = building.entrance[1] + Math.sin(angle) * spread;

      const asleep = live.isAsleep(slot);
      const followed = this.followed !== null && live.idOf[slot] === this.followed;
      let colour: number;
      if (followed) colour = C.AGENT_FOLLOWED;
      else if (asleep) colour = live.activity[slot] === ACTIVITY.DORMANT ? C.AGENT_DORMANT : C.AGENT_ASLEEP;
      else if (live.activity[slot] === ACTIVITY.LIGHT_IDLE) colour = C.AGENT_IDLE;
      else if (live.tier[slot] === TIER.PERSISTENT) colour = C.AGENT_PERSISTENT;
      else colour = C.AGENT_AWAKE;

      // Inference looks like inference: smaller, dimmer, never as solid as a fact.
      const alpha = derived ? 0.4 : 0.85;
      const size = (followed ? radius * 1.9 : radius) * (derived ? 0.78 : 1);

      g.circle(x, y, size).fill({ color: colour, alpha });
      if (followed) {
        g.circle(x, y, size * 3.2).stroke({ width: 0.8, color: C.AGENT_FOLLOWED, alpha: 0.85 });
      }
    }
  }

  private drawOverlay(model: CityModel, lod: Lod): void {
    const g = this.overlay;
    g.clear();
    const live = this.live;

    if (this.selection?.kind === "building") {
      const building = model.building(this.selection.id);
      if (building) {
        polyRect(g, building.x, building.y, building.width + 4, building.depth + 4, building.angle);
        g.stroke({ width: Math.max(0.8, 2 / this.camera.scale), color: C.SELECTION, alpha: 0.95 });
      }
    } else if (this.selection?.kind === "district") {
      const district = model.wire.districts[this.selection.index];
      if (district) {
        g.poly(district.polygon).stroke({
          width: Math.max(2, 3 / this.camera.scale),
          color: C.SELECTION,
          alpha: 0.8
        });
      }
    }

    if (!live) return;
    const now = live.tick;
    for (const event of this.events) {
      if (!event.anchor) continue;
      const age = now - event.tick;
      if (age < 0 || age > 36) continue;
      const fade = 1 - age / 36;
      const size = (8 + event.importance * 26) * (1 + (1 - fade) * 2.2);
      g.circle(event.anchor[0], event.anchor[1], size).stroke({
        width: Math.max(0.7, 1.6 / this.camera.scale),
        color: C.EVENT_PULSE,
        alpha: 0.10 + fade * 0.55 * (0.35 + event.importance)
      });
    }
  }

  private districtTint(id: string, kind: string): number {
    const base = C.DISTRICT_FILL[kind] ?? C.DISTRICT_FILL.mixed;
    if (!this.layer || this.layer.meta.scope !== "district") return base;
    const value = this.layer.values[id];
    if (value === undefined) return base;
    return C.rampColour(normalise(value, this.layer.meta), this.layer.meta.high_is_bad);
  }

  private buildingTint(building: BuildingView): number {
    if (this.layer && this.layer.meta.scope === "building") {
      const value = this.layer.values[building.id];
      if (value !== undefined) {
        return C.rampColour(normalise(value, this.layer.meta), this.layer.meta.high_is_bad);
      }
    }
    return C.buildingColour(building.kind);
  }
}

// -- helpers ------------------------------------------------------------------------

function normalise(value: number, meta: LayerMeta): number {
  const span = meta.high - meta.low;
  if (span <= 0) return 0;
  return Math.max(0, Math.min(1, (value - meta.low) / span));
}

function rectCorners(
  cx: number,
  cy: number,
  width: number,
  depth: number,
  angle: number
): [number, number][] {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const hw = width * 0.5;
  const hd = depth * 0.5;
  const local: [number, number][] = [
    [-hw, -hd],
    [hw, -hd],
    [hw, hd],
    [-hw, hd]
  ];
  return local.map(([x, y]) => [cx + x * c - y * s, cy + x * s + y * c] as [number, number]);
}

function polyRect(
  g: Graphics,
  cx: number,
  cy: number,
  width: number,
  depth: number,
  angle: number
): void {
  g.poly(rectCorners(cx, cy, width, depth, angle).flat());
}

function inRect(x: number, y: number, building: BuildingView): boolean {
  const c = Math.cos(-building.angle);
  const s = Math.sin(-building.angle);
  const dx = x - building.x;
  const dy = y - building.y;
  const lx = dx * c - dy * s;
  const ly = dx * s + dy * c;
  return Math.abs(lx) <= building.width * 0.5 && Math.abs(ly) <= building.depth * 0.5;
}

function pointInFlatPolygon(x: number, y: number, flat: number[]): boolean {
  let inside = false;
  const n = flat.length / 2;
  for (let i = 0, j = n - 1; i < n; j = i, i += 1) {
    const xi = flat[i * 2];
    const yi = flat[i * 2 + 1];
    const xj = flat[j * 2];
    const yj = flat[j * 2 + 1];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function mixColour(a: number, b: number, t: number): number {
  return C.mix(a, b, Math.max(0, Math.min(1, t)));
}
