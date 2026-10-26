/**
 * Reading a Wild Rift champion select out of a phone screen, for any phone.
 *
 * A screenshot or a mirrored phone (AirPlay, scrcpy, Phone Link, a capture
 * card) is read in the browser: nothing installed, iPhone included.
 *
 * THE LAYOUT (October 2026 UI, measured by circle detection over 600 frames
 * of four recorded drafts; wrdraft-overlay/tools/read_v2.py is the reference
 * implementation and its numbers are these):
 *
 *   Everything is sized by screen HEIGHT and pinned to an EDGE. Team rows sit
 *   at 0.1889 + 0.1333 i of the height; an ally portrait is 0.1889 H from the
 *   left edge, or 0.2556 H when its row shows summoner spells; an enemy
 *   portrait is the mirror image from the right edge. Bans are small circles
 *   along the top, 0.1556 H + 0.0798 H i from each edge.
 *
 * So the same numbers fit a 16:9 phone and a 21:9 one. What differs between
 * phones is how far in from each physical edge the game starts drawing: a
 * notch or rounded-corner safe area. That is the per-phone setting, two
 * insets, which calibrate() measures from a frame and the page stores per
 * screen shape. On simulated phones from 16:9 to 21:9 with notches on either
 * side it found the inset within 1 px every time.
 *
 * THE PHASE decides what the top strip means: bans during banning and
 * picking, the ten PICKS in the preparation phase (the side columns are gone
 * by then, and a last pick can go straight there without ever showing in a
 * column). It is read off the title at the top centre.
 */

export const PATCH = 32;
/** Compare only the inner part of a circle: a picking or locked-in player
 *  gets a thick gold ring, which is player STATE, not the champion's art. */
const ROUND_MASK = 0.85;
/** The winner must be this close and beat the runner-up by MARGIN. */
const ACCEPT = 0.5;
const MARGIN = 0.15;
/** Each slot is hunted over a small sweep around where it should be. */
const SEARCH = 0.22;
const SEARCH_STEPS = 3;

const ROW_Y = [0, 1, 2, 3, 4].map((i) => 0.1889 + 0.1333 * i);
const PORTRAIT = 0.104;
const PORTRAIT_X = [0.1889, 0.2556];          // without / with summoner spells
const BAN_Y = 0.05;
const BAN_D = 0.065;
const BAN_X = [0, 1, 2, 3, 4].map((i) => 0.1556 + 0.0798 * i);

export type Side = "L" | "R";
export type SlotGroup = "ban" | "ally" | "enemy";

export interface Slot {
  key: string;            // "ally 3", "enemy ban 2"
  side: Side;
  /** Candidate distances from that edge, in units of height. */
  offsets: number[];
  cy: number;
  size: number;
  group: SlotGroup;
  index: number;
}

export const SLOTS: Slot[] = [
  ...BAN_X.flatMap((x, i): Slot[] => [
    { key: `ally ban ${i + 1}`, side: "L", offsets: [x], cy: BAN_Y, size: BAN_D, group: "ban", index: i },
    { key: `enemy ban ${i + 1}`, side: "R", offsets: [x], cy: BAN_Y, size: BAN_D, group: "ban", index: i },
  ]),
  ...ROW_Y.flatMap((y, i): Slot[] => [
    { key: `ally ${i + 1}`, side: "L", offsets: PORTRAIT_X, cy: y, size: PORTRAIT, group: "ally", index: i },
    { key: `enemy ${i + 1}`, side: "R", offsets: PORTRAIT_X, cy: y, size: PORTRAIT, group: "enemy", index: i },
  ]),
];

/**
 * Where this device draws the draft UI: pixels in from each edge (negative
 * when a crop cuts into the UI, as in a cropped stream or screenshot) and the
 * UI scale. Phones are scale 1. Tablets draw the draft smaller: two iPad
 * streams measured 0.80 and 0.82, with the team columns centred vertically
 * and the top strip still pinned to the top edge.
 */
export interface Insets { left: number; right: number; scale: number }
export const NO_INSETS: Insets = { left: 0, right: 0, scale: 1 };

export function slotCenterX(slot: Slot, offset: number, w: number, h: number, insets: Insets): number {
  const d = insets.scale * offset * h;
  return slot.side === "L" ? insets.left + d : w - insets.right - d;
}

export function slotCenterY(slot: Slot, h: number, insets: Insets): number {
  return slot.group === "ban"
    ? insets.scale * slot.cy * h
    : ((1 - insets.scale) / 2 + insets.scale * slot.cy) * h;
}

export function slotSize(slot: Slot, h: number, insets: Insets): number {
  return Math.max(8, Math.round(insets.scale * slot.size * h));
}

// ---------------------------------------------------------------- references

export interface Reference {
  name: string;
  /** 16 px vector, for the coarse calibration pass. */
  vec16: Float32Array;
  /** Not a champion: an empty seat, a helmet, a role icon, or what a slot
   *  shows at its OTHER candidate offset. A placeholder win means "empty",
   *  which is what keeps an empty jungle seat from reading as Poppy. */
  placeholder: boolean;
  vec: Float32Array;
}

function circleMask(size: number): Uint8Array {
  const r = (size / 2 - 1) * ROUND_MASK;
  const out = new Uint8Array(size * size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = x - size / 2, dy = y - size / 2;
      out[y * size + x] = dx * dx + dy * dy <= r * r ? 1 : 0;
    }
  }
  return out;
}

const MASKS: Record<number, Uint8Array> = { [PATCH]: circleMask(PATCH), 16: circleMask(16) };

/** Mean-centre and scale to unit length over the circle's pixels. A flat
 *  patch becomes all zeros and so correlates with nothing. */
export function normalise(rgba: Uint8ClampedArray, patch = PATCH): Float32Array {
  const mask = MASKS[patch];
  let count = 0;
  for (const m of mask) count += m;
  const out = new Float32Array(count * 3);
  let k = 0;
  let sum = 0;
  for (let i = 0, p = 0; i < patch * patch; i++, p += 4) {
    if (!mask[i]) continue;
    out[k++] = rgba[p];
    out[k++] = rgba[p + 1];
    out[k++] = rgba[p + 2];
    sum += rgba[p] + rgba[p + 1] + rgba[p + 2];
  }
  const mean = sum / out.length;
  let sq = 0;
  for (let i = 0; i < out.length; i++) {
    out[i] -= mean;
    sq += out[i] * out[i];
  }
  const norm = Math.sqrt(sq);
  if (norm < 1e-6) return out.fill(0);
  for (let i = 0; i < out.length; i++) out[i] /= norm;
  return out;
}

function dot(a: Float32Array, b: Float32Array): number {
  let d = 0;
  for (let i = 0; i < a.length; i++) d += a[i] * b[i];
  return d;
}

/** Load one image and pre-normalise it. */
export async function loadReference(name: string, url: string, placeholder: boolean): Promise<Reference> {
  const img = new Image();
  // The champion CDN and our own copies allow cross-origin reads; without
  // this the canvas is tainted and the first pixel read throws.
  img.crossOrigin = "anonymous";
  img.src = url;
  await img.decode();
  const c = document.createElement("canvas");
  c.width = PATCH;
  c.height = PATCH;
  const ctx = c.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0, PATCH, PATCH);
  const vec = normalise(ctx.getImageData(0, 0, PATCH, PATCH).data);
  ctx.clearRect(0, 0, PATCH, PATCH);
  ctx.drawImage(img, 0, 0, 16, 16);
  return { name, placeholder, vec, vec16: normalise(ctx.getImageData(0, 0, 16, 16).data, 16) };
}

/** The reader's own assets: placeholder art and the phase titles. */
export interface ReaderAssets {
  /** Title mask size, and where to look for it: [top fraction of height,
   *  half-width as a fraction of height]. */
  size: [number, number];
  search: [number, number];
  phases: Record<string, string>;
  placeholders: string[];
}

export async function loadReaderAssets(): Promise<{ assets: ReaderAssets; placeholders: Reference[] }> {
  const assets = (await (await fetch("/draft-reader/reader.json")).json()) as ReaderAssets;
  const placeholders = await Promise.all(
    assets.placeholders.map((file) => loadReference(file.replace(/\.png$/, ""), `/draft-reader/ph/${file}`, true)),
  );
  return { assets, placeholders };
}

// ---------------------------------------------------------------- matching

export interface Match {
  name: string | null;
  placeholder: boolean;
  diff: number;
  margin: number;
}

const NO_MATCH: Match = { name: null, placeholder: false, diff: 1, margin: 0 };

/** The best reference at one exact box. */
function bestAt(
  ctx: CanvasRenderingContext2D, scratch: CanvasRenderingContext2D,
  x: number, y: number, size: number, refs: Reference[], patch = PATCH,
): Match {
  const { width: w, height: h } = ctx.canvas;
  if (x < 0 || y < 0 || x + size > w || y + size > h || size < 4) return NO_MATCH;
  scratch.clearRect(0, 0, patch, patch);
  scratch.drawImage(ctx.canvas, x, y, size, size, 0, 0, patch, patch);
  const win = normalise(scratch.getImageData(0, 0, patch, patch).data, patch);
  let best = Infinity, second = Infinity, bestRef: Reference | null = null;
  for (const ref of refs) {
    const d = 1 - dot(win, patch === PATCH ? ref.vec : ref.vec16);
    if (d < best) {
      // The runner-up must be a DIFFERENT answer.
      if (bestRef && bestRef.name !== ref.name) second = best;
      best = d;
      bestRef = ref;
    } else if (d < second && bestRef && ref.name !== bestRef.name) {
      second = d;
    }
  }
  if (!bestRef) return NO_MATCH;
  return { name: bestRef.name, placeholder: bestRef.placeholder, diff: best, margin: second - best };
}

const confident = (m: Match) => m.name != null && m.diff < ACCEPT && m.margin > MARGIN;

/**
 * One candidate offset: the centre first (with calibrated insets it is nearly
 * always right), then the sweep only if the centre was not a clear answer. A
 * clear PLACEHOLDER at the centre is a clear answer too -- an empty seat --
 * which keeps empty slots from paying for the whole sweep.
 */
function readAt(
  ctx: CanvasRenderingContext2D, scratch: CanvasRenderingContext2D,
  slot: Slot, offset: number, refs: Reference[], insets: Insets,
): Match {
  const { width: w, height: h } = ctx.canvas;
  const size = slotSize(slot, h, insets);
  const x0 = Math.round(slotCenterX(slot, offset, w, h, insets) - size / 2);
  const y0 = Math.round(slotCenterY(slot, h, insets) - size / 2);
  const centre = bestAt(ctx, scratch, x0, y0, size, refs);
  if (confident(centre)) return centre;
  // The BEST position over the whole sweep, as the Python reference does. The
  // first version returned the first confident match it met, and a window
  // half off the ban circle can be confidently wrong: the sample frame read
  // Volibear and lost Hwei and Senna that way.
  let best = centre;
  const step = Math.max(1, Math.round((size * SEARCH) / SEARCH_STEPS));
  for (let dy = -SEARCH_STEPS; dy <= SEARCH_STEPS; dy++) {
    for (let dx = -SEARCH_STEPS; dx <= SEARCH_STEPS; dx++) {
      if (dx === 0 && dy === 0) continue;
      const m = bestAt(ctx, scratch, x0 + dx * step, y0 + dy * step, size, refs);
      if (m.diff < best.diff) best = m;
    }
  }
  return best;
}

/**
 * A slot's champion, or null when it holds none.
 *
 * Each candidate offset is judged ON ITS OWN. Comparing them by raw distance
 * let a placeholder at the wrong offset beat the champion at the right one: a
 * row with summoner spells, looked at 0.067 H too far left, shows the spells
 * and half a portrait, which matched the "spells + ring" placeholder more
 * closely than Varus matched Varus.
 */
export function readSlot(
  ctx: CanvasRenderingContext2D, scratch: CanvasRenderingContext2D,
  slot: Slot, refs: Reference[], insets: Insets,
): Match {
  let champ: Match | null = null;
  let nearest: Match = NO_MATCH;
  for (const offset of slot.offsets) {
    const m = readAt(ctx, scratch, slot, offset, refs, insets);
    if (m.diff < nearest.diff) nearest = m;
    if (confident(m) && !m.placeholder && (!champ || m.diff < champ.diff)) champ = m;
  }
  return champ ?? { ...nearest, name: null };
}

export type SlotReads = Record<string, Match>;

export function readSlots(
  ctx: CanvasRenderingContext2D, scratch: CanvasRenderingContext2D,
  refs: Reference[], insets: Insets,
): SlotReads {
  const out: SlotReads = {};
  for (const slot of SLOTS) out[slot.key] = readSlot(ctx, scratch, slot, refs, insets);
  return out;
}

// ---------------------------------------------------------------- calibration

/** Largest inset searched, and the deepest crop, in units of height. Further
 *  in, the slots sit on the champion GRID, whose square portraits outscore
 *  the real column of helmets. */
const MAX_INSET = 0.12;
const MIN_INSET = -0.16;

/** Placeholders with real STRUCTURE (helmets, empty-ban circles, role icons
 *  in rings). Calibration scores only against these and the champions: the
 *  rest are near-featureless, and a wrong scale put small windows on plain
 *  backdrop, matched those almost perfectly, and won. */
const CAL_PLACEHOLDERS = new Set(["00", "01", "02", "06", "10", "11", "12", "22", "24", "28", "32", "46"]);

export function calibrationRefs(refs: Reference[]): Reference[] {
  return refs.filter((r) => !r.placeholder || CAL_PLACEHOLDERS.has(r.name.split("_")[1] ?? ""));
}

/** How much a side's slots look like ANY known image at this fit. A wrong
 *  fit puts every window half on the panel and half off, and nothing matches. */
function sideScore(
  ctx: CanvasRenderingContext2D, scratch: CanvasRenderingContext2D,
  side: Side, inset: number, scale: number, refs: Reference[], patch: number,
): number {
  const { width: w, height: h } = ctx.canvas;
  const fit: Insets = side === "L" ? { left: inset, right: 0, scale } : { left: 0, right: inset, scale };
  let total = 0;
  for (const slot of SLOTS) {
    if (slot.side !== side) continue;
    const size = slotSize(slot, h, fit);
    let best = 1;
    for (const offset of slot.offsets) {
      const x = Math.round(slotCenterX(slot, offset, w, h, fit) - size / 2);
      const y = Math.round(slotCenterY(slot, h, fit) - size / 2);
      best = Math.min(best, bestAt(ctx, scratch, x, y, size, refs, patch).diff);
    }
    total += best;
  }
  return -total;
}

function bestFit(
  ctx: CanvasRenderingContext2D, scratch: CanvasRenderingContext2D, refs: Reference[],
  scales: number[], grid: (side: Side) => number[], patch: number,
): Insets {
  let best: { score: number; fit: Insets } | null = null;
  for (const scale of scales) {
    let score = 0;
    const found: Record<Side, number> = { L: 0, R: 0 };
    for (const side of ["L", "R"] as const) {
      let top = -Infinity;
      for (const inset of grid(side)) {
        const s = sideScore(ctx, scratch, side, inset, scale, refs, patch);
        if (s > top) { top = s; found[side] = inset; }
      }
      score += top;
    }
    if (!best || score > best.score) best = { score, fit: { left: found.L, right: found.R, scale } };
  }
  return best!.fit;
}

/**
 * This device's fit, measured off one champion-select frame, in two passes
 * (wrdraft-overlay/tools/read_v2.py calibrate_fast is the reference, checked
 * against an exhaustive search on eight devices):
 *
 *   coarse  16 px patches, scale 0.70-1.02 in 0.04, insets in 1% of height
 *   fine    32 px patches, scale +-0.03 in 0.01, insets +-1.5% in 1 px
 *
 * A 16 px patch blurs a peak only a pixel or two wide, so the coarse step no
 * longer steps over it. Results: phones scale 1 with their notch inset to the
 * pixel, the iPad streams 0.81, a side-cropped stream about -0.09.
 */
export function calibrate(
  ctx: CanvasRenderingContext2D, scratch: CanvasRenderingContext2D, refs: Reference[],
): Insets {
  const h = ctx.canvas.height;
  const cal = calibrationRefs(refs);
  const step = Math.max(1, Math.round(0.01 * h));
  const coarseGrid: number[] = [];
  for (let i = Math.round(MIN_INSET * h); i <= Math.round(MAX_INSET * h); i += step) coarseGrid.push(i);
  const coarse = bestFit(ctx, scratch, cal, [0, 1, 2, 3, 4, 5, 6, 7, 8].map((i) => +(0.70 + 0.04 * i).toFixed(2)),
                         () => coarseGrid, 16);
  const span = Math.round(0.015 * h);
  const around = (c: number) => Array.from({ length: 2 * span + 1 }, (_, k) => c - span + k);
  return bestFit(ctx, scratch, cal, [-3, -2, -1, 0, 1, 2, 3].map((k) => +(coarse.scale + 0.01 * k).toFixed(2)),
                 (side) => around(side === "L" ? coarse.left : coarse.right), PATCH);
}

/** Several measurements of one device into one: the median of each number.
 *  A single frame occasionally mis-measures (a tooltip over the column, the
 *  ban row shifted by one circle); the median of three does not. */
export function medianFit(fits: Insets[]): Insets {
  const med = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };
  return { left: med(fits.map((f) => f.left)), right: med(fits.map((f) => f.right)), scale: med(fits.map((f) => f.scale)) };
}

// ---------------------------------------------------------------- phase

export type Phase =
  | "lane" | "prepick" | "banning" | "my_ban" | "bans"
  | "ally_pick" | "enemy_pick" | "my_pick" | "waiting" | "preparation" | "unknown";

/** Phases whose top strip holds BANS. In preparation it holds the PICKS. */
const TOP_IS_BANS = new Set<Phase>(["lane", "prepick", "banning", "my_ban", "bans", "ally_pick", "enemy_pick", "my_pick", "waiting"]);

function maskVector(raw: ArrayLike<number>): Float32Array {
  const out = new Float32Array(raw.length);
  let sum = 0;
  for (let i = 0; i < raw.length; i++) { out[i] = raw[i] / 255; sum += out[i]; }
  const mean = sum / raw.length;
  let sq = 0;
  for (let i = 0; i < out.length; i++) { out[i] -= mean; sq += out[i] * out[i]; }
  const n = Math.sqrt(sq);
  if (n < 1e-6) return out.fill(0);
  for (let i = 0; i < out.length; i++) out[i] /= n;
  return out;
}

export function phaseExamples(assets: ReaderAssets): { phase: Phase; vec: Float32Array }[] {
  return Object.entries(assets.phases).map(([phase, b64]) => {
    const bin = atob(b64);
    const raw = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) raw[i] = bin.charCodeAt(i);
    return { phase: phase as Phase, vec: maskVector(raw) };
  });
}

/** Box blur with OpenCV's default border (reflect, edge pixel not repeated). */
function boxBlur(src: Float32Array, w: number, h: number, k: number): Float32Array {
  const r = k >> 1;
  const refl = (i: number, n: number) => {
    if (n === 1) return 0;
    while (i < 0 || i >= n) i = i < 0 ? -i : 2 * n - 2 - i;
    return i;
  };
  const tmp = new Float32Array(w * h), out = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let s = 0;
      for (let d = -r; d <= r; d++) s += src[y * w + refl(x + d, w)];
      tmp[y * w + x] = s / k;
    }
  }
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let s = 0;
      for (let d = -r; d <= r; d++) s += tmp[refl(y + d, h) * w + x];
      out[y * w + x] = s / k;
    }
  }
  return out;
}

/** Area-weighted resize of a 0/1 mask (Pillow's BOX filter), to 0-255. */
function boxResize(src: Uint8Array, sw: number, sh: number, tw: number, th: number): Float32Array {
  const weights = (sn: number, tn: number) => Array.from({ length: tn }, (_, t) => {
    const a = (t * sn) / tn, b = ((t + 1) * sn) / tn;
    const ws: [number, number][] = [];
    for (let i = Math.floor(a); i < Math.ceil(b); i++) ws.push([i, Math.min(b, i + 1) - Math.max(a, i)]);
    const sum = ws.reduce((x, [, v]) => x + v, 0);
    return ws.map(([i, v]) => [i, v / sum] as [number, number]);
  });
  const wx = weights(sw, tw), wy = weights(sh, th);
  const out = new Float32Array(tw * th);
  for (let ty = 0; ty < th; ty++) {
    for (let tx = 0; tx < tw; tx++) {
      let s = 0;
      for (const [yy, vy] of wy[ty]) for (const [xx, vx] of wx[tx]) s += src[yy * sw + xx] * vy * vx;
      out[ty * tw + tx] = 255 * s;
    }
  }
  return out;
}

/** A true title scores 0.5-1.0 against its example; every wrong one 0.1-0.2. */
const PHASE_ACCEPT = 0.45;
const PHASE_MARGIN = 0.25;

/**
 * The phase, from the title at the top centre (wrdraft-overlay/tools/read_v2.py
 * title_mask_v2 is the reference). Scale-free: the title is found, not
 * assumed at a fixed box, so phones, tablets and cropped streams all read.
 *
 *  - text is WHITE, and after a pick the animation behind it can be any
 *    colour, so pixels are scored on whiteness (their weakest channel) minus
 *    their neighbourhood's, which lifts the text over any hue or flash;
 *  - the title is the first band of rows from the top that crosses many
 *    letter strokes (splash art crosses few), grown sideways across word gaps;
 *  - that band, cut tight and shrunk, is compared with one example per phase.
 */
export function readPhase(
  ctx: CanvasRenderingContext2D, assets: ReaderAssets,
  examples: { phase: Phase; vec: Float32Array }[],
): { phase: Phase; score: number } {
  const unknown = { phase: "unknown" as Phase, score: 0 };
  const { width: W, height: H } = ctx.canvas;
  const [sy, hw] = assets.search;
  const [tw, th] = assets.size;
  const x0 = Math.max(0, Math.round(W / 2 - hw * H)), x1 = Math.min(W, Math.round(W / 2 + hw * H));
  const cw = x1 - x0, ch = Math.max(4, Math.round(sy * H));
  if (cw < 8) return unknown;
  const data = ctx.getImageData(x0, 0, cw, ch).data;
  const white = new Float32Array(cw * ch);
  for (let i = 0, p = 0; i < white.length; i++, p += 4) white[i] = Math.min(data[p], data[p + 1], data[p + 2]);
  const k = Math.max(3, Math.round(0.03 * H)) | 1;
  const bg = boxBlur(white, cw, ch, k);
  let sum = 0;
  for (let i = 0; i < white.length; i++) { white[i] -= bg[i]; sum += white[i]; }
  const mean = sum / white.length;
  let sq = 0;
  for (const g of white) sq += (g - mean) * (g - mean);
  const cut = mean + 1.8 * Math.sqrt(sq / white.length);
  const on = new Uint8Array(cw * ch);
  for (let i = 0; i < on.length; i++) on[i] = white[i] > cut ? 1 : 0;

  // Rows that cross many strokes.
  const tr = new Array<number>(ch).fill(0);
  for (let y = 0; y < ch; y++) for (let x = 1; x < cw; x++) tr[y] += on[y * cw + x] !== on[y * cw + x - 1] ? 1 : 0;
  const bar = Math.max(6, 0.4 * Math.max(...tr));
  const ys = tr.flatMap((v, y) => (v >= bar ? [y] : []));
  if (!ys.length) return unknown;
  const start = ys[0];
  let end = start;
  for (const y of ys.slice(1)) { if (y - end > 2) break; end = y; }
  const bh = end - start + 1;
  if (bh < 3) return unknown;

  // Sideways from the centre across word gaps.
  const has = new Uint8Array(cw);
  for (let y = start; y <= end; y++) for (let x = 0; x < cw; x++) if (on[y * cw + x]) has[x] = 1;
  const gap = Math.max(3, Math.round(0.03 * H));
  const any = (a: number, b: number) => { for (let i = Math.max(0, a); i < Math.min(cw, b); i++) if (has[i]) return true; return false; };
  const cx = Math.floor(cw / 2);
  let lo = cx, hi = cx;
  while (lo > 0 && any(lo - gap, lo)) lo--;
  while (hi < cw - 1 && any(hi + 1, hi + 1 + gap)) hi++;
  let c0 = -1, c1 = -1;
  for (let x = lo; x <= hi; x++) if (has[x]) { if (c0 < 0) c0 = x; c1 = x; }
  if (c0 < 0) return unknown;
  const bw = c1 - c0 + 1;
  const band = new Uint8Array(bw * bh);
  for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) band[y * bw + x] = on[(start + y) * cw + c0 + x];

  const vec = maskVector(boxResize(band, bw, bh, tw, th));
  const scores = examples.map((ex) => ({ phase: ex.phase, score: dot(vec, ex.vec) })).sort((a, b) => b.score - a.score);
  const [first, second] = scores;
  if (!first) return unknown;
  return first.score >= PHASE_ACCEPT && first.score - (second?.score ?? 0) >= PHASE_MARGIN
    ? first : { phase: "unknown", score: first.score };
}

// ---------------------------------------------------------------- the draft

export interface ScanResult {
  phase: Phase;
  bans: string[];
  /** The ten ban circles by seat: your team's five, then theirs. Both teams
   *  can ban the same champion, so this keeps duplicates that `bans` drops. */
  banSeats: (string | null)[];
  allies: string[];
  enemies: string[];
}

/** A read counts once it held this many usable frames in a row: wrong reads
 *  in the recordings were 1-6 frame flickers during animations. */
const STABLE = 2;
/** A pick slot showing EMPTY this many frames running is cleared: allies
 *  pre-pick and enemies hover, both visible in this UI, and a pre-pick that
 *  gets banned leaves the seat empty again. Bans are never cleared. */
const CLEAR = 3;

/**
 * The draft as it stands, built up frame by frame.
 *
 * Measured on four recorded drafts with this exact logic: every champion of
 * all four drafts held correctly at the end (79 of 79), 0.87% of held reads
 * wrong at any moment, and most of those were real hovers rather than
 * misreads.
 */
export class DraftTracker {
  private state = new Map<string, string>();
  private streak = new Map<string, { name: string | null; n: number }>();

  reset() {
    this.state.clear();
    this.streak.clear();
  }

  /** Feed one frame's slot reads and phase; returns the draft as it stands.
   *  `single` is for a lone screenshot, where there is no next frame to
   *  confirm a read against. */
  update(reads: SlotReads, phase: Phase, single = false): ScanResult {
    const stable = single ? 1 : STABLE;
    if (phase !== "unknown") {
      for (const slot of SLOTS) {
        const name = reads[slot.key]?.name ?? null;
        let key: string | null = null;
        if (slot.group === "ban") {
          if (TOP_IS_BANS.has(phase)) key = slot.key;
          // The strip lists each team in its own order and shows SKINS, so in
          // preparation it only ADDS, keyed apart from the columns.
          else if (phase === "preparation") key = `${slot.side === "L" ? "ally" : "enemy"} prep ${slot.index + 1}`;
        } else if (TOP_IS_BANS.has(phase)) {
          key = slot.key;
        }
        if (!key) continue;
        const prev = this.streak.get(key);
        const n = prev && prev.name === name ? prev.n + 1 : 1;
        this.streak.set(key, { name, n });
        if (name && n >= stable) this.state.set(key, name);
        else if (!name && n >= CLEAR && !key.includes(" ban ") && !key.includes(" prep ")) this.state.delete(key);
      }
    }
    const out: ScanResult = { phase, bans: [], banSeats: [], allies: [], enemies: [] };
    for (const side of ["ally", "enemy"]) {
      for (let i = 1; i <= 5; i++) out.banSeats.push(this.state.get(`${side} ban ${i}`) ?? null);
    }
    const seen = new Set<string>();
    for (const [key, name] of this.state) {
      const bucket = key.includes(" ban ") ? out.bans : key.startsWith("ally") ? out.allies : out.enemies;
      const tag = `${bucket === out.bans ? "b" : key.startsWith("ally") ? "a" : "e"}:${name}`;
      if (seen.has(tag)) continue;     // a column read and its prep-strip twin
      seen.add(tag);
      bucket.push(name);
    }
    return out;
  }
}

/**
 * Trim letterbox bars from a captured frame. Sharing a whole desktop puts the
 * phone mirror in the middle with black around it, and every position above
 * is measured against the phone screen alone.
 */
export function contentRect(ctx: CanvasRenderingContext2D): { x: number; y: number; w: number; h: number } {
  const { width: w, height: h } = ctx.canvas;
  const data = ctx.getImageData(0, 0, w, h).data;
  const dark = (x: number, y: number) => {
    const p = (y * w + x) * 4;
    return data[p] + data[p + 1] + data[p + 2] < 60;
  };
  const rowDark = (y: number) => {
    for (let x = 0; x < w; x += Math.max(1, Math.floor(w / 40))) if (!dark(x, y)) return false;
    return true;
  };
  const colDark = (x: number) => {
    for (let y = 0; y < h; y += Math.max(1, Math.floor(h / 40))) if (!dark(x, y)) return false;
    return true;
  };
  let top = 0, bottom = h - 1, left = 0, right = w - 1;
  while (top < bottom && rowDark(top)) top++;
  while (bottom > top && rowDark(bottom)) bottom--;
  while (left < right && colDark(left)) left++;
  while (right > left && colDark(right)) right--;
  return { x: left, y: top, w: right - left + 1, h: bottom - top + 1 };
}

export const READER = { PATCH, ACCEPT, MARGIN, ROUND_MASK, SEARCH, SEARCH_STEPS, MAX_INSET, MIN_INSET };
