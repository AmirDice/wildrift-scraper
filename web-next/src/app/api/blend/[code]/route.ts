import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, readSession } from "@/lib/session";
import { computeBlend, joinBlend } from "@/lib/albums";
import { memoryUploadsEnabled } from "@/lib/memory-upload";

/**
 * GET  -> the computed blend (pending until the second player joins).
 * POST -> joins the blend as the second player.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: RouteContext<"/api/blend/[code]">) {
  const { code } = await context.params;
  const blend = await computeBlend(code);
  if (!blend) return NextResponse.json({ error: "blend not found" }, { status: 404 });

  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  return NextResponse.json(
    {
      blend,
      // Whether the viewer is already one of the two players decides if the page
      // shows "join this blend" or just the result.
      isMember: Boolean(user && (user.sub === blend.a.sub || user.sub === blend.b?.sub)),
      // The memory uploader hides itself when no blob store is configured.
      uploadsEnabled: memoryUploadsEnabled(),
    },
    { headers: { "Cache-Control": "private, no-store, max-age=0" } },
  );
}

export async function POST(_request: Request, context: RouteContext<"/api/blend/[code]">) {
  const { code } = await context.params;
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });

  const result = await joinBlend(code, user);
  if ("error" in result) return NextResponse.json(result, { status: 409 });
  return NextResponse.json({ blend: await computeBlend(code) });
}
