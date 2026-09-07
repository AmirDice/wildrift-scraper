/**
 * Reading a Wild Rift champion select out of a mirrored phone screen.
 *
 * The Android overlay reads the draft off the phone itself. That costs an APK
 * sideload, which measured out as the step where the install funnel dies --
 * roughly 200 download clicks became 60 installs -- and it reaches no iPhone at
 * all. A PC second screen reads the same pixels out of a mirror window instead:
 * AirPlay, scrcpy, Phone Link, a USB capture, anything that puts the phone on
 * the desktop. Nothing is installed on the phone, and iOS is included.
 *
 * Two things had to be true for this to work, and both were measured against
 * the 112 calibration frames from a real draft before any of it was written:
 *
 * The slot geometry is FRACTIONS of the screen, so it has to survive being
 * scaled into a window. It does: across a 5.5x size range, from the native
 * 1080px-wide frame down to a 194px thumbnail, match distance moved from 0.543
 * to 0.541 and the number of slots successfully identified stayed flat at
 * 77-81. Scaling is not what breaks this.
 *
 * And the matcher COULD afford to be better here than on the phone. The
 * overlay compares 32x32 patches because it runs on a phone CPU every 400ms;
 * at that size fourteen pairs of champion portraits sit closer than 0.40 and
 * are liable to be confused, falling to three at 64 and one at 96 -- Poppy and
 * Senna, genuinely near-identical at any resolution. A desktop has the budget.
 * See PATCH below for why that upgrade is not switched on yet.
 */

/**
 * Patch size for comparison.
 *
 * 64 separates the roster better -- fourteen dangerously-close portrait pairs
 * at 32 fall to three at 64 -- and a desktop has the CPU for it. It is NOT
 * enabled, because ACCEPT and MARGIN below were measured at 32 and do not
 * transfer: at 64 every distance shifts up about 0.07 and the margins on
 * genuine matches fall under the threshold. Measured on a real frame, Kai'Sa
 * matched at margin 0.148 and Diana at 0.124 against a 0.15 bar, so the reader
 * silently dropped reads it had actually got right.
 *
 * Raising this is a real accuracy win and needs its own calibration pass
 * against labelled frames first. Until then it matches the phone, where these
 * thresholds were measured.
 */
const PATCH = 32;
/** How much of the circle to compare. The player currently picking gets a
 *  thick gold flame ring, and that is a player STATE, not the champion's art. */
const ROUND_MASK = 0.85;
/** The winner must be this close, and beat the runner-up by MARGIN. ACCEPT
 *  only rules out the absurd; MARGIN is what actually discriminates. */
const ACCEPT = 0.5;
const MARGIN = 0.15;
/** Layout fractions are read off screenshots and a different device will not
 *  agree to the pixel, so each slot is hunted over a small sweep. */
const SEARCH = 0.22;
const SEARCH_STEPS = 4;

const TEAM_PITCH = 0.1361;
const BAN_PITCH = 0.037;

export type SlotGroup = "ban" | "ally" | "enemy";

export interface Slot {
  cx: number;
  cy: number;
  size: number;
  round: boolean;
  group: SlotGroup;
}

function column(cx: number, group: SlotGroup): Slot[] {
  return Array.from({ length: 5 }, (_, i) => ({
    cx, cy: 0.1898 + TEAM_PITCH * i, size: 0.1, round: true, group,
  }));
}

/** The top strip, which during banning and picking holds the BANS. */
function banStrip(): Slot[] {
  const out: Slot[] = [];
  for (let i = 0; i < 5; i++) {
    out.push({ cx: 0.0718 + BAN_PITCH * i, cy: 0.05, size: 0.0625, round: true, group: "ban" });
    out.push({ cx: 0.7808 + BAN_PITCH * i, cy: 0.05, size: 0.0625, round: true, group: "ban" });
  }
  return out;
}

/** The ban summary screen: two big centred rows, ally over opponent. */
function banSummary(): Slot[] {
  const xs = [0.354, 0.427, 0.5, 0.573, 0.646];
  return [0.339, 0.628].flatMap((cy) =>
    xs.map((cx) => ({ cx, cy, size: 0.108, round: false, group: "ban" as SlotGroup })));
}

export const SLOTS: Slot[] = [
  ...banStrip(),
  ...banSummary(),
  ...column(0.1179, "ally"),
  ...column(0.9141, "enemy"),
];

// ---------------------------------------------------------------- references

export interface Reference {
  name: string;
  /** Not a champion: a role icon in an unlocked seat, or empty-seat art. The
   *  matcher answers with its nearest reference and nothing else, so without
   *  these an empty slot comes back as whichever champion it resembles -- and
   *  confidently, because a role icon is a real image and not a smudge. */
  placeholder: boolean;
  round: Float64Array;
  square: Float64Array;
}

function circleMask(size: number): boolean[] {
  const r = (size / 2 - 1) * ROUND_MASK;
  const out: boolean[] = [];
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = x - size / 2, dy = y - size / 2;
      out.push(dx * dx + dy * dy <= r * r);
    }
  }
  return out;
}

const MASK = circleMask(PATCH);

/**
 * Mean-centre and scale to unit length, over the shape's own pixels.
 *
 * A patch with no variation becomes all zeros and so correlates with nothing,
 * which is the right answer for blank sky.
 */
export function normalise(rgba: Uint8ClampedArray, round: boolean): Float64Array {
  const vals: number[] = [];
  for (let i = 0, p = 0; i < PATCH * PATCH; i++, p += 4) {
    if (round && !MASK[i]) continue;
    vals.push(rgba[p], rgba[p + 1], rgba[p + 2]);
  }
  const out = new Float64Array(vals.length);
  let sum = 0;
  for (const v of vals) sum += v;
  const mean = vals.length ? sum / vals.length : 0;
  let sq = 0;
  for (let i = 0; i < vals.length; i++) {
    out[i] = vals[i] - mean;
    sq += out[i] * out[i];
  }
  const norm = Math.sqrt(sq);
  if (norm < 1e-6) return out.fill(0);
  for (let i = 0; i < out.length; i++) out[i] /= norm;
  return out;
}

function dot(a: Float64Array, b: Float64Array): number {
  let d = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) d += a[i] * b[i];
  return d;
}

/** Load one image and pre-normalise it in both slot shapes. */
export async function loadReference(
  name: string, url: string, placeholder: boolean,
): Promise<Reference> {
  const img = new Image();
  // The champion CDN sends Access-Control-Allow-Origin: *, so the canvas is
  // not tainted and getImageData works. Without this the whole approach dies
  // on a SecurityError at the first pixel read.
  img.crossOrigin = "anonymous";
  img.src = url;
  await img.decode();
  const c = document.createElement("canvas");
  c.width = PATCH;
  c.height = PATCH;
  const ctx = c.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0, PATCH, PATCH);
  const data = ctx.getImageData(0, 0, PATCH, PATCH).data;
  return { name, placeholder, round: normalise(data, true), square: normalise(data, false) };
}

// ---------------------------------------------------------------- matching

export interface Match {
  name: string | null;
  diff: number;
  margin: number;
}

/** The champion at one exact box, or null when nothing wins clearly. */
export function matchAt(
  ctx: CanvasRenderingContext2D, scratch: CanvasRenderingContext2D,
  x: number, y: number, size: number, round: boolean, refs: Reference[],
): Match {
  const { width: w, height: h } = ctx.canvas;
  if (x < 0 || y < 0 || x + size > w || y + size > h || size < 4) {
    return { name: null, diff: 1, margin: 0 };
  }
  scratch.clearRect(0, 0, PATCH, PATCH);
  scratch.drawImage(ctx.canvas, x, y, size, size, 0, 0, PATCH, PATCH);
  const win = normalise(scratch.getImageData(0, 0, PATCH, PATCH).data, round);

  let best = Infinity, second = Infinity, bestRef: Reference | null = null;
  for (const ref of refs) {
    const d = 1 - dot(win, round ? ref.round : ref.square);
    if (d < best) {
      // The runner-up must be a DIFFERENT answer, or the placeholders veto
      // each other: there are three jungle role icons scoring within 0.02.
      if (bestRef && bestRef.name !== ref.name) second = best;
      best = d;
      bestRef = ref;
    } else if (d < second && bestRef && ref.name !== bestRef.name) {
      second = d;
    }
  }
  if (!bestRef || best >= ACCEPT || second - best <= MARGIN) {
    return { name: null, diff: best, margin: second - best };
  }
  return {
    name: bestRef.placeholder ? null : bestRef.name,
    diff: best,
    margin: second - best,
  };
}

/** One slot, hunted over the sweep. Centre first: it is usually right, and
 *  trying it first keeps the common case cheap. Returns the winning distance
 *  as well, because the caller has to compare readings across slots. */
function readSlot(
  ctx: CanvasRenderingContext2D, scratch: CanvasRenderingContext2D,
  slot: Slot, refs: Reference[],
): Match {
  const { width: w, height: h } = ctx.canvas;
  const size = Math.round(slot.size * w);
  const x0 = Math.round(slot.cx * w - size / 2);
  const y0 = Math.round(slot.cy * h - size / 2);
  const hit = matchAt(ctx, scratch, x0, y0, size, slot.round, refs);
  if (hit.name) return hit;
  const step = Math.max(1, Math.round((size * SEARCH) / SEARCH_STEPS));
  for (let dy = -SEARCH_STEPS; dy <= SEARCH_STEPS; dy++) {
    for (let dx = -SEARCH_STEPS; dx <= SEARCH_STEPS; dx++) {
      if (dx === 0 && dy === 0) continue;
      const m = matchAt(ctx, scratch, x0 + dx * step, y0 + dy * step,
                        size, slot.round, refs);
      if (m.name) return m;
    }
  }
  return { name: null, diff: 1, margin: 0 };
}

export interface ScanResult {
  bans: string[];
  allies: string[];
  enemies: string[];
}

/**
 * One champion, one bucket.
 *
 * A name read in two places keeps only its best-scoring reading: a draft that
 * bans someone and then also picks them is wrong on its face. The ban strip
 * and the ban summary are two views of the same bans, which is the usual
 * reason a name shows up twice.
 */
export function scanFrame(
  ctx: CanvasRenderingContext2D, scratch: CanvasRenderingContext2D, refs: Reference[],
): ScanResult {
  // Read everything first, then resolve. Taking the FIRST slot that claims a
  // name is wrong, because SLOTS is ordered bans-then-teams: a champion who
  // matched weakly in a ban slot was filed as banned before his real pick slot
  // was ever looked at. Observed doing exactly that to Pantheon.
  const best = new Map<string, { group: SlotGroup; diff: number }>();
  for (const slot of SLOTS) {
    const hit = readSlot(ctx, scratch, slot, refs);
    if (!hit.name) continue;
    const prev = best.get(hit.name);
    if (!prev || hit.diff < prev.diff) {
      best.set(hit.name, { group: slot.group, diff: hit.diff });
    }
  }
  const out: ScanResult = { bans: [], allies: [], enemies: [] };
  for (const [name, { group }] of best) {
    const bucket = group === "ban" ? out.bans
      : group === "ally" ? out.allies : out.enemies;
    bucket.push(name);
  }
  return out;
}

/**
 * Trim letterbox bars from a captured frame.
 *
 * Sharing a whole desktop puts the phone mirror in the middle of a landscape
 * screen with black on either side, and every fraction above would then be
 * measured against the wrong rectangle. Sharing the mirror WINDOW avoids this
 * entirely, which is what the UI should ask for -- this is the safety net for
 * when someone shares the screen anyway.
 */
export function contentRect(
  ctx: CanvasRenderingContext2D,
): { x: number; y: number; w: number; h: number } {
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

export const READER = { PATCH, ACCEPT, MARGIN, ROUND_MASK, SEARCH, SEARCH_STEPS };
