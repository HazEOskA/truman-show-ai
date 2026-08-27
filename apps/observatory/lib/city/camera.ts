/**
 * The camera: world metres in, screen pixels out.
 *
 * Hydra is drawn in a fixed 2:1 dimetric projection -- the classic isometric-looking view
 * where one world unit east goes two pixels right and one pixel down. The choice is not
 * decorative. A top-down plan cannot show that a tower is taller than a shed, and a real 3D
 * camera would make the viewer manage an orbit before they can read anything. Dimetric gives
 * height for free, keeps every building the same shape wherever it sits, and needs exactly
 * two controls: pan and zoom.
 *
 * The projection is deliberately *not* rotatable. A city you can spin is a city where the
 * viewer has to re-find north every time they look away, and readability beats spectacle
 * here.
 */

import type { Bounds } from "./types";

/** Screen pixels per world metre at zoom 1. */
export const BASE_SCALE = 0.5;
export const MIN_ZOOM = 0.06;
export const MAX_ZOOM = 6.0;

export interface Viewport {
  width: number;
  height: number;
}

export class Camera {
  /** Where the camera is looking, in world metres. */
  x = 0;
  y = 0;
  zoom = 1;
  width = 1;
  height = 1;

  resize(viewport: Viewport): void {
    this.width = Math.max(1, viewport.width);
    this.height = Math.max(1, viewport.height);
  }

  get scale(): number {
    return BASE_SCALE * this.zoom;
  }

  /** World metres -> screen pixels. The 2:1 dimetric transform, and the only one. */
  toScreen(x: number, y: number): [number, number] {
    const s = this.scale;
    const sx = (x - this.x) * s;
    const sy = (y - this.y) * s;
    return [this.width * 0.5 + (sx - sy), this.height * 0.5 + (sx + sy) * 0.5];
  }

  /** Screen pixels -> world metres. Needed for click picking and for pan. */
  toWorld(px: number, py: number): [number, number] {
    const s = this.scale;
    const dx = px - this.width * 0.5;
    const dy = py - this.height * 0.5;
    // Invert [sx - sy, (sx + sy) / 2].
    const sx = dx * 0.5 + dy;
    const sy = dy - dx * 0.5;
    return [this.x + sx / s, this.y + sy / s];
  }

  /** How tall one metre of building is on screen. Height is drawn straight up. */
  get verticalScale(): number {
    return this.scale * 0.82;
  }

  panByScreen(dx: number, dy: number): void {
    const s = this.scale;
    const sx = -dx * 0.5 - dy;
    const sy = -dy + dx * 0.5;
    this.x += sx / s;
    this.y += sy / s;
  }

  /** Zoom about a screen point, so the thing under the cursor stays under the cursor. */
  zoomAt(px: number, py: number, factor: number): void {
    const [wx, wy] = this.toWorld(px, py);
    this.zoom = clamp(this.zoom * factor, MIN_ZOOM, MAX_ZOOM);
    const [ax, ay] = this.toWorld(px, py);
    this.x += wx - ax;
    this.y += wy - ay;
  }

  /** Frame a world-space box, with a little room around it. */
  frame(bounds: Bounds, padding = 1.12): void {
    const cx = (bounds.min_x + bounds.max_x) * 0.5;
    const cy = (bounds.min_y + bounds.max_y) * 0.5;
    const w = Math.max(1, bounds.max_x - bounds.min_x) * padding;
    const h = Math.max(1, bounds.max_y - bounds.min_y) * padding;

    // In dimetric, a w x h box occupies (w + h) horizontally and (w + h) / 2 vertically.
    const spanX = (w + h) * BASE_SCALE;
    const spanY = ((w + h) * 0.5) * BASE_SCALE;
    this.zoom = clamp(Math.min(this.width / spanX, this.height / spanY), MIN_ZOOM, MAX_ZOOM);
    this.x = cx;
    this.y = cy;
  }

  centreOn(x: number, y: number): void {
    this.x = x;
    this.y = y;
  }

  /** World-space box currently visible, generously padded for culling. */
  visibleBounds(margin = 200): Bounds {
    const corners: [number, number][] = [
      this.toWorld(0, 0),
      this.toWorld(this.width, 0),
      this.toWorld(0, this.height),
      this.toWorld(this.width, this.height)
    ];
    const xs = corners.map((c) => c[0]);
    const ys = corners.map((c) => c[1]);
    return {
      min_x: Math.min(...xs) - margin,
      min_y: Math.min(...ys) - margin,
      max_x: Math.max(...xs) + margin,
      max_y: Math.max(...ys) + margin
    };
  }
}

export function clamp(value: number, low: number, high: number): number {
  return value < low ? low : value > high ? high : value;
}

/**
 * Level of detail.
 *
 * Which things are worth drawing depends only on how many pixels a metre is worth.
 *
 * The thresholds are calibrated against Hydra rather than guessed. Its built fabric spans
 * about 5.6 km, so framing the whole city in a nine-hundred-pixel canvas lands at roughly
 * 0.08 pixels per metre. An earlier ladder put the first rung at 0.09 and the default view
 * therefore showed nothing but arterial roads -- technically correct and completely useless.
 * Quarter has to start below wherever "the whole city, framed" falls.
 */
export enum Lod {
  /** Pulled right out: districts and trunk roads only. */
  Region = 0,
  /** The whole city at once: blocks, building masses, crowds as density. */
  Quarter = 1,
  /** Streets: individual buildings, agents as dots. */
  Street = 2,
  /** Close: addresses, entrances, agents distinguishable. */
  Close = 3
}

export function lodFor(scale: number): Lod {
  if (scale < 0.04) return Lod.Region;
  if (scale < 0.16) return Lod.Quarter;
  if (scale < 0.6) return Lod.Street;
  return Lod.Close;
}
