import { NextResponse } from "next/server";
import { KV_CONFIGURED } from "@/lib/kv";
import { ALPHA_GATE, listCodes, mintCodes, releaseCode } from "@/lib/alpha";

/**
 * The alpha tester list: mint codes, see who used them, take one back.
 *
 *   GET  /api/admin/alpha?token=...            list every code and its device
 *   POST /api/admin/alpha?token=...  {mint:10, note:"discord wave 1"}
 *   POST /api/admin/alpha?token=...  {release:"WRABCD2345"}
 *
 * Guarded by ADMIN_TOKEN and 404 without one, like the usage read-out and the
 * notify list. A code is not a secret worth much on its own, but the LIST is:
 * it is every unused code at once.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function denied(request: Request): boolean {
  const expected = (process.env.ADMIN_TOKEN ?? "").trim();
  const provided = new URL(request.url).searchParams.get("token") ?? "";
  return !expected || provided !== expected;
}

export async function GET(request: Request) {
  if (denied(request)) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (!KV_CONFIGURED) return NextResponse.json({ error: "no KV configured" }, { status: 503 });

  const codes = await listCodes();
  const used = codes.filter((c) => c.device);
  return NextResponse.json({
    gate: ALPHA_GATE,
    // The number the whole feature exists to control, first.
    testers: used.length,
    minted: codes.length,
    spare: codes.length - used.length,
    codes,
  });
}

export async function POST(request: Request) {
  if (denied(request)) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (!KV_CONFIGURED) return NextResponse.json({ error: "no KV configured" }, { status: 503 });

  let body: { mint?: number; note?: string; release?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  if (body.release) {
    const ok = await releaseCode(body.release);
    return NextResponse.json({ ok, released: body.release },
                             { status: ok ? 200 : 404 });
  }

  // Capped per call: a slipped keystroke on a number should not mint ten
  // thousand codes into a list that is then read back in full.
  const count = Math.max(1, Math.min(100, Math.floor(Number(body.mint) || 0)));
  if (!body.mint) return NextResponse.json({ error: "nothing to do" }, { status: 400 });
  const minted = await mintCodes(count, String(body.note ?? "").slice(0, 80));
  return NextResponse.json({ minted: minted.length, codes: minted.map((c) => c.code) });
}
