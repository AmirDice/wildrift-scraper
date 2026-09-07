"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { roster } from "@/lib/threat";
import {
  contentRect, loadReference, scanFrame, READER,
  type Reference, type ScanResult,
} from "@/lib/screen-read";

/**
 * Reads a mirrored phone screen and reports the draft it finds.
 *
 * The phone-side overlay needs an APK sideloaded, which is where its install
 * funnel dies and which reaches no iPhone at all. This reads the same pixels
 * from a mirror window on the desktop instead -- AirPlay, scrcpy, Phone Link,
 * a USB capture -- so nothing is installed on the phone and iOS is included.
 *
 * The browser's own share picker is the permission prompt, which people
 * already recognise from video calls rather than from a Play Protect warning.
 */
export function SecondScreen() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const frameRef = useRef<HTMLCanvasElement | null>(null);
  const patchRef = useRef<HTMLCanvasElement | null>(null);
  const refsRef = useRef<Reference[] | null>(null);
  const timerRef = useRef<number | null>(null);
  const frames = useRef(0);

  const [status, setStatus] = useState("Load the champion icons to begin.");
  const [ready, setReady] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [tick, setTick] = useState({ ms: 0, count: 0 });
  // What the reader is actually looking at. Without this a live mirror that
  // reads nothing is indistinguishable from a live mirror that is framed
  // wrong, and the second is far more likely: a shared WINDOW carries its own
  // chrome, and the slot fractions are measured against the phone screen
  // alone.
  const [shot, setShot] = useState<{ url: string; rect: string } | null>(null);

  // The icons are the reference set: 141 champion portraits, normalised once
  // and reused every frame. Normalising inside the match loop would redo all
  // of them for every slot at every candidate position.
  const loadIcons = useCallback(async () => {
    setStatus("Loading champion icons...");
    const rows = Object.values(roster());
    const out: Reference[] = [];
    let failed = 0;
    // Our own copy first. The CDN original takes about 1.2s each from
    // Europe, and 141 of those sequentially is nearly three minutes -- the
    // reader never finished loading, which looked exactly like it was broken.
    // Loaded in parallel now too, since same-origin has no six-per-host wall.
    const settled = await Promise.allSettled(rows.map((r) => {
      const url = (r as { iconLocal?: string }).iconLocal || r.icon;
      return url ? loadReference(r.name, url, false) : Promise.reject(new Error("no icon"));
    }));
    for (const s of settled) {
      if (s.status === "fulfilled") out.push(s.value);
      else failed += 1;
    }
    refsRef.current = out;
    setReady(out.length > 0);
    setStatus(`${out.length} champion icons ready${failed ? `, ${failed} failed` : ""}. `
      + "Now share the window your phone is mirrored into.");
  }, []);

  /**
   * Read one known champion-select frame and report what it finds.
   *
   * The reader has a lot of moving parts -- icon CORS, canvas pixel access,
   * the normalise maths, the slot fractions -- and when a live mirror produces
   * nothing it is not obvious which of them failed. This exercises every one
   * of them against a frame whose answer is known, so "the reader is broken"
   * and "the mirror is framed wrong" stop looking the same.
   */
  const selfTest = useCallback(async () => {
    if (!refsRef.current?.length) return;
    setStatus("Running the sample frame...");
    try {
      const img = new Image();
      img.src = "/_testframe.jpg";
      await img.decode();
      const c = document.createElement("canvas");
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      const ctx = c.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(img, 0, 0);
      const t0 = performance.now();
      const result = scanFrame(
        ctx, patchRef.current!.getContext("2d", { willReadFrequently: true })!,
        refsRef.current,
      );
      setTick({ ms: Math.round(performance.now() - t0), count: 1 });
      setScan(result);
      const found = [...result.bans, ...result.allies, ...result.enemies];
      setStatus(`Sample frame (${img.naturalWidth}x${img.naturalHeight}): read `
        + `${found.length} champions -- ${found.join(", ") || "none"}.`);
    } catch (err) {
      setStatus(`Sample frame failed: ${(err as Error).message}`);
    }
  }, []);

  const stop = useCallback(() => {
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = null;
    const v = videoRef.current;
    const stream = v?.srcObject as MediaStream | null;
    stream?.getTracks().forEach((t) => t.stop());
    if (v) v.srcObject = null;
    setSharing(false);
    setStatus("Stopped.");
  }, []);

  const share = useCallback(async () => {
    if (!refsRef.current?.length) return;
    try {
      // Share the mirror WINDOW rather than the whole screen: the slot
      // positions are fractions of the phone's screen, and a whole desktop
      // puts that screen in the middle of a landscape frame with black bars
      // on either side. contentRect below trims those when it can, but not
      // needing to is better.
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: 4 }, audio: false,
      });
      const v = videoRef.current!;
      v.srcObject = stream;
      await v.play();
      stream.getVideoTracks()[0].addEventListener("ended", stop);
      setSharing(true);
      setStatus("Reading. Open champion select on your phone.");

      timerRef.current = window.setInterval(() => {
        const frame = frameRef.current, patch = patchRef.current;
        if (!frame || !patch || !v.videoWidth) return;
        frame.width = v.videoWidth;
        frame.height = v.videoHeight;
        const ctx = frame.getContext("2d", { willReadFrequently: true })!;
        ctx.drawImage(v, 0, 0);

        // Trim letterboxing, then read the trimmed region as if it were the
        // whole phone screen.
        const rect = contentRect(ctx);
        let readCtx = ctx;
        if (rect.w > 32 && rect.h > 32
            && (rect.w < frame.width * 0.98 || rect.h < frame.height * 0.98)) {
          const crop = document.createElement("canvas");
          crop.width = rect.w;
          crop.height = rect.h;
          const cctx = crop.getContext("2d", { willReadFrequently: true })!;
          cctx.drawImage(frame, rect.x, rect.y, rect.w, rect.h, 0, 0, rect.w, rect.h);
          readCtx = cctx;
        }

        const t0 = performance.now();
        const result = scanFrame(readCtx, patch.getContext("2d", { willReadFrequently: true })!,
                                 refsRef.current!);
        setTick((prev) => ({ ms: Math.round(performance.now() - t0), count: prev.count + 1 }));
        setScan(result);

        // A thumbnail of exactly the pixels being read, every couple of
        // seconds. If the phone screen does not fill this, the share is
        // wrong -- not the reader.
        if (frames.current % 3 === 0) {
          const thumb = document.createElement("canvas");
          thumb.width = 150;
          thumb.height = Math.max(1, Math.round(150 * readCtx.canvas.height / readCtx.canvas.width));
          thumb.getContext("2d")!.drawImage(readCtx.canvas, 0, 0, thumb.width, thumb.height);
          setShot({
            url: thumb.toDataURL("image/jpeg", 0.6),
            rect: `${readCtx.canvas.width}x${readCtx.canvas.height}`
              + (readCtx === ctx ? " (whole share)" : ` trimmed from ${frame.width}x${frame.height}`),
          });
        }
        frames.current += 1;
      }, 600);
    } catch (err) {
      setStatus(`Share cancelled or unavailable: ${(err as Error).message}`);
    }
  }, [stop]);

  useEffect(() => () => stop(), [stop]);

  const row = (label: string, names: string[]) => (
    <div className="mt-3">
      <div className="text-[0.65rem] font-bold uppercase tracking-wide text-muted">
        {label} <span className="text-faint">({names.length})</span>
      </div>
      <div className="mt-1 text-sm">{names.length ? names.join(" · ") : <span className="text-faint">nothing read yet</span>}</div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button
          onClick={loadIcons}
          disabled={ready}
          className="rounded-lg border border-gold/40 px-3 py-2 text-sm font-semibold disabled:opacity-40"
        >
          1. Load icons
        </button>
        <button
          onClick={share}
          disabled={!ready || sharing}
          className="rounded-lg border border-gold/40 px-3 py-2 text-sm font-semibold disabled:opacity-40"
        >
          2. Share the mirror window
        </button>
        {sharing && (
          <button onClick={stop} className="rounded-lg border border-red-500/50 px-3 py-2 text-sm font-semibold">
            Stop
          </button>
        )}
        <button
          onClick={selfTest}
          disabled={!ready}
          className="rounded-lg border border-white/20 px-3 py-2 text-sm disabled:opacity-40"
        >
          Test on a sample frame
        </button>
      </div>

      <p className="text-sm text-muted">{status}</p>

      {sharing && (
        <p className="text-xs text-faint">
          {tick.count} frames read, {tick.ms}ms each, {READER.PATCH}px patches.
        </p>
      )}

      {shot && (
        <div className="flex items-start gap-3 rounded-xl border border-white/10 p-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={shot.url} alt="what the reader sees" className="rounded border border-white/15" />
          <div className="text-xs text-faint">
            <div className="font-bold text-muted">What the reader sees</div>
            <div className="mt-1">{shot.rect}</div>
            <div className="mt-2 max-w-xs">
              The phone screen should fill this box edge to edge. If you can see the
              mirror app&apos;s toolbar or desktop around it, share just the mirror
              window instead.
            </div>
          </div>
        </div>
      )}

      {scan && (
        <div className="glass rounded-xl border border-white/10 p-4">
          {row("Bans", scan.bans)}
          {row("Their picks", scan.enemies)}
          {row("Your team", scan.allies)}
        </div>
      )}

      {/* The capture pipeline. The video is the stream, the first canvas is
          the frame being read, the second is the 64px scratch every patch is
          scaled into before comparison. */}
      <video ref={videoRef} className="hidden" playsInline muted />
      <canvas ref={frameRef} className="hidden" />
      <canvas ref={patchRef} width={READER.PATCH} height={READER.PATCH} className="hidden" />
    </div>
  );
}
