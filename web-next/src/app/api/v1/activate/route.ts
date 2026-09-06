import { NextResponse } from "next/server";
import { KV_CONFIGURED } from "@/lib/kv";
import { ALPHA_GATE, deviceAllowed, redeem } from "@/lib/alpha";

/**
 * POST /api/v1/activate  { code }  with x-device-id
 *
 * The overlay calls this once, before anything else works. It is separate from
 * the build endpoint on purpose: activation must be answerable while the app
 * has no data and no quota, and a tester typing their code should get a plain
 * yes or no rather than a build error.
 *
 * GET on the same path reports whether THIS device is already in, which is how
 * the app decides whether to show the code screen at all.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function device(request: Request): string {
  return request.headers.get("x-device-id") || "";
}

export async function GET(request: Request) {
  const id = device(request);
  return NextResponse.json({
    gate: ALPHA_GATE,
    activated: await deviceAllowed(id),
    // Nothing works without a device id, and a tester should be told that
    // rather than shown a code box that can never succeed.
    device: Boolean(id),
  });
}

export async function POST(request: Request) {
  let body: { code?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const id = device(request);
  if (!id) {
    return NextResponse.json(
      { error: "this build cannot identify itself. Reinstall the app." }, { status: 400 });
  }
  if (!KV_CONFIGURED) {
    // Saying "accepted" when nothing was stored would let a tester through
    // once and lock them out on the next launch.
    return NextResponse.json({ error: "activation is unavailable right now" }, { status: 503 });
  }

  const result = await redeem(body.code ?? "", id);
  if (result.ok) {
    return NextResponse.json({ ok: true, already: result.already });
  }
  const message = {
    "unknown-code": "That code is not one of ours.",
    "code-taken": "That code is already in use on another phone.",
    "bad-request": "Enter the code exactly as it was given to you.",
    "no-store": "Activation is unavailable right now.",
  }[result.reason];
  return NextResponse.json({ error: message },
                           { status: result.reason === "no-store" ? 503 : 400 });
}
