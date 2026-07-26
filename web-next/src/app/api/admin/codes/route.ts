import { NextResponse } from "next/server";
import { createCode, deleteCode, listCodes, setCodeActive, type AccessKind } from "@/lib/access";

/**
 * Access-code administration, guarded by ADMIN_TOKEN.
 *
 *   GET    ?token=...                       -> every code with its click and
 *                                              sign-in counts
 *   POST   ?token=...  { kind, label, ... } -> mint one
 *   PATCH  ?token=...  { code, active }     -> turn one off without losing its
 *                                              stats
 *   DELETE ?token=...&code=...              -> remove it entirely
 *
 * With no ADMIN_TOKEN configured the route 404s rather than defaulting open:
 * this mints credentials.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function authorised(request: Request): boolean {
  const expected = process.env.ADMIN_TOKEN ?? "";
  if (!expected) return false;
  const provided = new URL(request.url).searchParams.get("token")
    ?? request.headers.get("x-admin-token")
    ?? "";
  return provided === expected;
}

const denied = () => NextResponse.json({ error: "not found" }, { status: 404 });

export async function GET(request: Request) {
  if (!authorised(request)) return denied();
  return NextResponse.json(
    { codes: await listCodes() },
    { headers: { "Cache-Control": "private, no-store, max-age=0" } },
  );
}

export async function POST(request: Request) {
  if (!authorised(request)) return denied();

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const kind: AccessKind = body.kind === "referral" ? "referral" : "beta";
  const label = typeof body.label === "string" ? body.label : "";
  if (!label.trim()) {
    return NextResponse.json({ error: "label is required, so the code is identifiable later" }, { status: 400 });
  }

  const record = await createCode({
    kind,
    label,
    grantsBeta: typeof body.grantsBeta === "boolean" ? body.grantsBeta : undefined,
    unlimitedBuilds: body.unlimitedBuilds === true,
    expiresAt: typeof body.expiresAt === "string" ? body.expiresAt : null,
    maxUses: typeof body.maxUses === "number" && body.maxUses > 0 ? Math.floor(body.maxUses) : null,
  });

  return NextResponse.json({ code: record, url: `https://wrtruemeta.com/i/${record.code}` });
}

export async function PATCH(request: Request) {
  if (!authorised(request)) return denied();

  let body: { code?: unknown; active?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const code = typeof body.code === "string" ? body.code : "";
  if (!code) return NextResponse.json({ error: "code is required" }, { status: 400 });

  const record = await setCodeActive(code, body.active !== false);
  if (!record) return NextResponse.json({ error: "no such code" }, { status: 404 });
  return NextResponse.json({ code: record });
}

export async function DELETE(request: Request) {
  if (!authorised(request)) return denied();
  const code = new URL(request.url).searchParams.get("code") ?? "";
  if (!code) return NextResponse.json({ error: "code is required" }, { status: 400 });
  const ok = await deleteCode(code);
  if (!ok) return NextResponse.json({ error: "no such code" }, { status: 404 });
  return NextResponse.json({ ok: true });
}
