"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { roster } from "@/lib/threat";
import {
  calibrate, contentRect, DraftTracker, loadReaderAssets, loadReference, medianFit, phaseExamples,
  readPhase, readSlots, slotCenterX, slotCenterY, slotSize, NO_INSETS, READER, SLOTS,
  type Insets, type Phase, type ReaderAssets, type Reference, type ScanResult,
} from "@/lib/screen-read";

/**
 * Reads champion select off a picture of the phone screen, on any phone.
 *
 * TWO WAYS IN. A SCREENSHOT needs no mirroring software, no cable and no
 * install, on iPhone and Android alike. A LIVE MIRROR (AirPlay, Phone Link,
 * scrcpy) reads continuously for anyone already mirroring.
 *
 * PER-PHONE SETUP. The layout is the same on every phone except how far in
 * from each edge the game starts drawing (a notch or safe area). The first
 * champion-select frame from a new screen shape is measured automatically
 * (calibrate in lib/screen-read), saved in this browser per screen shape, and
 * shown as an alignment overlay that can be nudged by hand if a phone ever
 * needs it.
 */

const SETUP_KEY = "wrtm-phone-setup-v2";
/** Phases in which both side columns are on screen, so a frame can be measured. */
const MEASURABLE = new Set<Phase>(["prepick", "banning", "my_ban", "ally_pick", "enemy_pick", "my_pick", "waiting"]);

/** left/right are fractions of height (so a resized mirror window keeps
 *  them); scale is the draft UI scale, 1 on phones, ~0.8 on tablets. */
interface Setup { left: number; right: number; scale: number; auto: boolean; at: string }

/** Measurements taken from separate frames before a live setup is settled. */
const CONSENSUS = 3;

/** Screens are told apart by shape, not size: a mirror window can be any size,
 *  but the insets scale with height, so they are stored as fractions of it. */
const shapeKey = (w: number, h: number) => (w / h).toFixed(3);

function loadSetups(): Record<string, Setup> {
  try { return JSON.parse(localStorage.getItem(SETUP_KEY) ?? "{}") as Record<string, Setup>; } catch { return {}; }
}
function saveSetup(key: string, setup: Setup) {
  try { localStorage.setItem(SETUP_KEY, JSON.stringify({ ...loadSetups(), [key]: setup })); } catch { /* private mode */ }
}

const PHASE_LABEL: Record<Phase, string> = {
  lane: "Lane assignment", prepick: "Pre-pick", banning: "Banning", my_ban: "Your ban", bans: "Ban summary",
  ally_pick: "Your team picking", enemy_pick: "Opponents picking", my_pick: "Your pick",
  waiting: "Waiting for others", preparation: "Preparation", unknown: "Not champion select",
};

export function SecondScreen({ onScan, onPreview }: {
  /** Called with every read: the second-screen page fills the draft board.
   *  `live` reads carry the whole tracked draft and are mirrored onto it; a
   *  screenshot only adds to what is already there. */
  onScan?: (scan: ScanResult & { live?: boolean }) => void;
  /** What the reader is looking at, for the board to show: the live stream
   *  while sharing, the screenshot after one is read, null once stopped. */
  onPreview?: (preview: { stream?: MediaStream; image?: string } | null) => void;
} = {}) {
  const previewRef = useRef(onPreview);
  useEffect(() => { previewRef.current = onPreview; }, [onPreview]);
  const shotUrlRef = useRef<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const frameRef = useRef<HTMLCanvasElement | null>(null);
  const patchRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const refsRef = useRef<Reference[] | null>(null);
  const assetsRef = useRef<{ assets: ReaderAssets; examples: ReturnType<typeof phaseExamples> } | null>(null);
  const trackerRef = useRef(new DraftTracker());
  const lastFrameRef = useRef<HTMLCanvasElement | null>(null);
  const timerRef = useRef<number | null>(null);

  const [status, setStatus] = useState("Loading champion icons...");
  const [ready, setReady] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [tick, setTick] = useState({ ms: 0, count: 0 });
  const [phase, setPhase] = useState<Phase | null>(null);
  const [dragging, setDragging] = useState(false);
  // The current screen shape and its setup, as fractions of height.
  const [shape, setShape] = useState<{ key: string; w: number; h: number } | null>(null);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [showAlign, setShowAlign] = useState(false);
  const onScanRef = useRef(onScan);
  useEffect(() => { onScanRef.current = onScan; }, [onScan]);
  const setupRef = useRef<Setup | null>(null);
  useEffect(() => { setupRef.current = setup; }, [setup]);
  // Live measurements of the current screen shape, settled by median.
  const pendingRef = useRef<{ key: string; fits: Insets[] }>({ key: "", fits: [] });

  const loadIcons = useCallback(async () => {
    setStatus("Loading champion icons...");
    const rows = Object.values(roster());
    // Our own copies, in parallel: the CDN originals took ~1.2s each.
    const [settled, readerAssets] = await Promise.all([
      Promise.allSettled(rows.map((r) => {
        const url = (r as { iconLocal?: string }).iconLocal || r.icon;
        return url ? loadReference(r.name, url, false) : Promise.reject(new Error("no icon"));
      })),
      loadReaderAssets().catch(() => null),
    ]);
    const out: Reference[] = [];
    let failed = 0;
    for (const s of settled) {
      if (s.status === "fulfilled") out.push(s.value);
      else failed += 1;
    }
    if (readerAssets) {
      out.push(...readerAssets.placeholders);
      assetsRef.current = { assets: readerAssets.assets, examples: phaseExamples(readerAssets.assets) };
    }
    refsRef.current = out;
    setReady(out.length > 0 && Boolean(readerAssets));
    setStatus(readerAssets
      ? `${out.length - readerAssets.placeholders.length} champion icons ready${failed ? `, ${failed} failed` : ""}. `
        + "Drop in a screenshot of champion select, or share a live mirror."
      : "Could not load the reader's files. Reload the page to try again.");
  }, []);

  /** Draw the slot circles over the last frame, so a setup can be checked by eye. */
  const drawOverlay = useCallback(() => {
    const src = lastFrameRef.current, out = overlayRef.current;
    if (!src || !out) return;
    const w = 640, h = Math.round((640 * src.height) / src.width);
    out.width = w;
    out.height = h;
    const ctx = out.getContext("2d")!;
    ctx.drawImage(src, 0, 0, w, h);
    const s = setupRef.current;
    const insets = s ? { left: s.left * h, right: s.right * h, scale: s.scale } : NO_INSETS;
    for (const slot of SLOTS) {
      for (const offset of slot.offsets) {
        ctx.beginPath();
        ctx.arc(slotCenterX(slot, offset, w, h, insets), slotCenterY(slot, h, insets), slotSize(slot, h, insets) / 2, 0, Math.PI * 2);
        ctx.strokeStyle = slot.group === "ban" ? "rgba(255,90,90,.9)" : offset === slot.offsets[0] ? "rgba(114,167,255,.95)" : "rgba(114,167,255,.45)";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
  }, []);

  /**
   * Read one already-drawn frame: trim letterboxing, find the phase, make
   * sure this screen shape has a setup (measuring it if not), read, track.
   */
  const readCanvas = useCallback((ctx: CanvasRenderingContext2D, single: boolean): ScanResult | null => {
    const frame = ctx.canvas;
    const rect = contentRect(ctx);
    let readCtx = ctx;
    if (rect.w > 32 && rect.h > 32 && (rect.w < frame.width * 0.92 || rect.h < frame.height * 0.92)) {
      const crop = document.createElement("canvas");
      crop.width = rect.w;
      crop.height = rect.h;
      const cctx = crop.getContext("2d", { willReadFrequently: true })!;
      cctx.drawImage(frame, rect.x, rect.y, rect.w, rect.h, 0, 0, rect.w, rect.h);
      readCtx = cctx;
    }
    const scratch = patchRef.current!.getContext("2d", { willReadFrequently: true })!;
    const refs = refsRef.current!;
    const a = assetsRef.current!;
    const { width: w, height: h } = readCtx.canvas;
    const t0 = performance.now();

    const key = shapeKey(w, h);
    if (!shape || shape.key !== key) setShape({ key, w, h });
    let current = setupRef.current && shape?.key === key ? setupRef.current : loadSetups()[key] ?? null;
    const ph = readPhase(readCtx, a.assets, a.examples).phase;
    setPhase(ph);

    // Measure a screen shape the first time a draft frame from it arrives. A
    // live mirror settles on the median of three frames; the first answer is
    // used meanwhile, so reading starts at once. A screenshot measures itself.
    const pending = pendingRef.current;
    const settling = !single && pending.key === key && pending.fits.length < CONSENSUS;
    if ((!current || settling) && MEASURABLE.has(ph)) {
      const found = calibrate(readCtx, scratch, refs);
      const fit = { left: found.left / h, right: found.right / h, scale: found.scale };
      if (single) {
        current = { ...fit, auto: true, at: new Date().toISOString() };
        saveSetup(key, current);
      } else {
        if (pending.key !== key) pendingRef.current = { key, fits: [] };
        pendingRef.current.fits.push(fit);
        const settled = medianFit(pendingRef.current.fits);
        current = { ...settled, auto: true, at: new Date().toISOString() };
        if (pendingRef.current.fits.length >= CONSENSUS) saveSetup(key, current);
      }
    }
    if (current !== setupRef.current) setSetup(current);
    setupRef.current = current;
    const insets: Insets = current ? { left: current.left * h, right: current.right * h, scale: current.scale } : NO_INSETS;

    const reads = readSlots(readCtx, scratch, refs, insets);
    // Development only: every slot's raw read, for checking the reader
    // against the Python reference without guessing from the board.
    if (process.env.NODE_ENV === "development") {
      (window as unknown as { __draftReads?: unknown }).__draftReads = { phase: ph, insets, reads };
    }
    if (single) trackerRef.current.reset();
    const result = trackerRef.current.update(reads, ph, single);
    setTick((prev) => ({ ms: Math.round(performance.now() - t0), count: prev.count + 1 }));
    onScanRef.current?.({ ...result, live: !single });

    // Keep the frame for the alignment view.
    const keep = lastFrameRef.current ?? document.createElement("canvas");
    keep.width = w;
    keep.height = h;
    keep.getContext("2d")!.drawImage(readCtx.canvas, 0, 0);
    lastFrameRef.current = keep;
    drawOverlay();
    return result;
  }, [shape, drawOverlay]);

  /** A screenshot, from a file, a drag, or the clipboard. */
  const readShot = useCallback(async (file: Blob | null | undefined) => {
    if (!file) return;
    if (!refsRef.current?.length || !assetsRef.current) {
      setStatus("Still loading the champion icons; try again in a moment.");
      return;
    }
    setStatus("Reading the screenshot...");
    try {
      const bitmap = await createImageBitmap(file);
      const c = document.createElement("canvas");
      c.width = bitmap.width;
      c.height = bitmap.height;
      const ctx = c.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(bitmap, 0, 0);
      bitmap.close();
      const result = readCanvas(ctx, true);
      if (shotUrlRef.current) URL.revokeObjectURL(shotUrlRef.current);
      shotUrlRef.current = URL.createObjectURL(file);
      previewRef.current?.({ image: shotUrlRef.current });
      const found = result ? [...result.bans, ...result.allies, ...result.enemies] : [];
      setStatus(found.length
        ? `Read ${found.length} champions off the screenshot.`
        : "Nothing recognised in that screenshot. It has to be champion select, full screen, "
          + "taken with the phone's own screenshot rather than a photo of the screen.");
    } catch (err) {
      setStatus(`Could not read that image: ${(err as Error).message}`);
    }
  }, [readCanvas]);

  /** The sample frame: a known draft, so "the reader is broken" and "the
   *  mirror is framed wrong" stop looking the same. */
  const selfTest = useCallback(async () => {
    const res = await fetch("/_testframe.jpg");
    await readShot(await res.blob());
  }, [readShot]);

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = [...(e.clipboardData?.items ?? [])].find((i) => i.type.startsWith("image/"));
      if (item) {
        e.preventDefault();
        void readShot(item.getAsFile());
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [readShot]);

  const stop = useCallback(() => {
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = null;
    const v = videoRef.current;
    const stream = v?.srcObject as MediaStream | null;
    stream?.getTracks().forEach((t) => t.stop());
    if (v) v.srcObject = null;
    if (stream) previewRef.current?.(null);
    setSharing(false);
    setStatus("Stopped.");
  }, []);

  const share = useCallback(async () => {
    if (!refsRef.current?.length) return;
    try {
      // Share the mirror WINDOW: a whole desktop puts the phone in the middle
      // with black around it (trimmed when possible, but better avoided).
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 4 }, audio: false });
      const v = videoRef.current!;
      v.srcObject = stream;
      await v.play();
      stream.getVideoTracks()[0].addEventListener("ended", stop);
      previewRef.current?.({ stream });
      trackerRef.current.reset();
      setSharing(true);
      setStatus("Reading. Open champion select on your phone.");
      timerRef.current = window.setInterval(() => {
        const frame = frameRef.current;
        if (!frame || !patchRef.current || !v.videoWidth) return;
        frame.width = v.videoWidth;
        frame.height = v.videoHeight;
        const ctx = frame.getContext("2d", { willReadFrequently: true })!;
        ctx.drawImage(v, 0, 0);
        readCanvas(ctx, false);
      }, 600);
    } catch (err) {
      setStatus(`Share cancelled or unavailable: ${(err as Error).message}`);
    }
  }, [stop, readCanvas]);

  /** Manual setup: nudge one side (0.5% of height) or the size (0.01). */
  const nudge = (field: "left" | "right" | "scale", by: number) => {
    if (!shape) return;
    const base = setup ?? { left: 0, right: 0, scale: 1, auto: false, at: "" };
    const value = field === "scale"
      ? Math.max(0.6, Math.min(1.1, +(base.scale + by).toFixed(2)))
      : Math.max(READER.MIN_INSET, Math.min(READER.MAX_INSET, base[field] + by));
    const next = { ...base, [field]: value, auto: false, at: new Date().toISOString() };
    setSetup(next);
    setupRef.current = next;
    saveSetup(shape.key, next);
    drawOverlay();
  };

  /** Measure again from the last frame. */
  const remeasure = () => {
    const src = lastFrameRef.current;
    if (!src || !shape || !refsRef.current) return;
    const ctx = src.getContext("2d", { willReadFrequently: true })!;
    const found = calibrate(ctx, patchRef.current!.getContext("2d", { willReadFrequently: true })!, refsRef.current);
    const next = { left: found.left / src.height, right: found.right / src.height, scale: found.scale, auto: true, at: new Date().toISOString() };
    setSetup(next);
    setupRef.current = next;
    saveSetup(shape.key, next);
    drawOverlay();
  };

  useEffect(() => { void loadIcons(); }, [loadIcons]);
  useEffect(() => () => stop(), [stop]);
  useEffect(() => { if (showAlign) drawOverlay(); }, [showAlign, drawOverlay]);

  const px = (frac: number) => (shape ? Math.round(frac * shape.h) : 0);

  return (
    <div className="space-y-4">
      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); void readShot(e.dataTransfer.files?.[0]); }}
        className={`flex cursor-pointer flex-col items-center gap-1 rounded-2xl border-2 border-dashed p-6 text-center transition ${
          dragging ? "border-accent bg-accent/10" : "border-white/20 hover:border-accent/60"
        }`}
      >
        <input type="file" accept="image/*" className="hidden"
          onChange={(e) => { void readShot(e.target.files?.[0]); e.target.value = ""; }} />
        <span className="text-sm font-semibold text-text">
          {ready ? "Drop a champion select screenshot" : "Loading champion icons..."}
        </span>
        <span className="text-xs text-muted">
          or tap to pick one, or paste with Ctrl+V. On your phone, screenshot the draft and choose it
          here: nothing to install, iPhone included.
        </span>
      </label>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-faint">Already mirroring?</span>
        <button onClick={share} disabled={!ready || sharing}
          className="glass rounded-lg border border-gold/40 px-3 py-2 text-sm font-semibold disabled:opacity-40">
          Read a live mirror
        </button>
        {sharing && (
          <button onClick={stop} className="glass rounded-lg border border-red-500/50 px-3 py-2 text-sm font-semibold">Stop</button>
        )}
        <button onClick={() => void selfTest()} disabled={!ready}
          className="glass rounded-lg border border-white/20 px-3 py-2 text-sm disabled:opacity-40">
          Test on a sample frame
        </button>
      </div>

      <p className="text-sm text-muted">{status}</p>
      {phase && <p className="text-xs text-faint">Phase: <span className="font-semibold text-muted">{PHASE_LABEL[phase]}</span>
        {sharing ? ` · ${tick.count} frames read, ${tick.ms} ms each` : ` · read in ${tick.ms} ms`}</p>}

      {shape && (
        <div className="glass rounded-xl border border-white/10 p-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="font-semibold text-text">Phone setup</span>
              <span className="ml-2 text-faint">screen {shape.w}x{shape.h} ({shape.key}:1)</span>
              <div className="mt-0.5 text-muted">
                {setup
                  ? `${setup.auto ? "Measured automatically" : "Adjusted by hand"}: left ${px(setup.left)} px, right ${px(setup.right)} px, size ${Math.round(setup.scale * 100)}%${setup.scale < 0.95 ? " (tablet layout)" : ""}. Saved for this screen shape.`
                  : "Not set up yet: it is measured automatically from the first champion-select frame."}
              </div>
            </div>
            <button onClick={() => setShowAlign((v) => !v)} className="rounded-lg border border-white/20 px-2.5 py-1.5 font-semibold text-muted hover:text-text">
              {showAlign ? "Hide alignment" : "Check alignment"}
            </button>
          </div>
          {showAlign && (
            <div className="mt-3 space-y-2">
              <canvas ref={overlayRef} className="w-full max-w-[640px] rounded border border-white/15" />
              <p className="text-faint">The circles should sit on the portraits and ban icons. If a side is off, move it:</p>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-muted">Left side</span>
                <button onClick={() => nudge("left", -0.005)} className="rounded border border-white/20 px-2 py-1">&larr;</button>
                <button onClick={() => nudge("left", 0.005)} className="rounded border border-white/20 px-2 py-1">&rarr;</button>
                <span className="ml-3 text-muted">Right side</span>
                <button onClick={() => nudge("right", 0.005)} className="rounded border border-white/20 px-2 py-1">&larr;</button>
                <button onClick={() => nudge("right", -0.005)} className="rounded border border-white/20 px-2 py-1">&rarr;</button>
                <span className="ml-3 text-muted">Size</span>
                <button onClick={() => nudge("scale", -0.01)} className="rounded border border-white/20 px-2 py-1">&minus;</button>
                <button onClick={() => nudge("scale", 0.01)} className="rounded border border-white/20 px-2 py-1">+</button>
                <button onClick={remeasure} className="ml-3 rounded border border-accent/40 px-2.5 py-1 font-semibold text-accent">Measure again</button>
              </div>
            </div>
          )}
        </div>
      )}

      <video ref={videoRef} className="hidden" playsInline muted />
      <canvas ref={frameRef} className="hidden" />
      <canvas ref={patchRef} width={READER.PATCH} height={READER.PATCH} className="hidden" />
    </div>
  );
}
