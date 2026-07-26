import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, readSession } from "@/lib/session";
import {
  addBlendMemory, removeBlendMemory, setBlendBanner, computeBlend, isMemoryCategory,
} from "@/lib/albums";
import { uploadMemoryImage, memoryUploadsEnabled } from "@/lib/memory-upload";

/**
 * The duo's shared album, hanging off the blend.
 *
 *  POST   multipart { image, category, caption } -> uploads and adds a memory
 *  DELETE ?memoryId=...                          -> removes one
 *  PATCH  { bannerMemoryId }                      -> sets/clears the duo banner
 *
 * Every write returns the freshly COMPUTED blend, the same shape GET returns, so
 * the view can drop it straight into state. Membership (being one of the two
 * players) is enforced in the lib functions, which return null for outsiders.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request, context: RouteContext<"/api/blend/[code]/memories">) {
  const { code } = await context.params;
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });

  if (!memoryUploadsEnabled()) {
    return NextResponse.json(
      { error: "Image uploads are not enabled on this deployment yet." },
      { status: 501 },
    );
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "expected multipart form data" }, { status: 400 });
  }

  const category = form.get("category");
  if (!isMemoryCategory(category)) {
    return NextResponse.json({ error: "a valid category is required" }, { status: 400 });
  }
  const file = form.get("image");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "an image is required" }, { status: 400 });
  }

  const upload = await uploadMemoryImage(
    { type: file.type, size: file.size, bytes: await file.arrayBuffer(), name: file.name },
    code,
  );
  if (!upload.ok) return NextResponse.json({ error: upload.error }, { status: upload.status });

  const caption = form.get("caption");
  const result = await addBlendMemory(
    code,
    { sub: user.sub, name: user.name },
    {
      imageUrl: upload.url,
      category,
      caption: typeof caption === "string" ? caption : undefined,
    },
  );
  if (result === null) return NextResponse.json({ error: "not a member of this blend" }, { status: 403 });
  if ("error" in result) return NextResponse.json(result, { status: 409 });
  return NextResponse.json({ blend: await computeBlend(code) });
}

export async function DELETE(request: Request, context: RouteContext<"/api/blend/[code]/memories">) {
  const { code } = await context.params;
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });

  const memoryId = new URL(request.url).searchParams.get("memoryId") ?? "";
  if (!memoryId) return NextResponse.json({ error: "memoryId is required" }, { status: 400 });

  const record = await removeBlendMemory(code, user.sub, memoryId);
  if (!record) return NextResponse.json({ error: "not a member of this blend" }, { status: 403 });
  return NextResponse.json({ blend: await computeBlend(code) });
}

export async function PATCH(request: Request, context: RouteContext<"/api/blend/[code]/memories">) {
  const { code } = await context.params;
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });

  let body: { bannerMemoryId?: unknown };
  try {
    body = (await request.json()) as { bannerMemoryId?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const bannerMemoryId =
    body.bannerMemoryId === null ? null
    : typeof body.bannerMemoryId === "string" ? body.bannerMemoryId
    : undefined;
  if (bannerMemoryId === undefined) {
    return NextResponse.json({ error: "bannerMemoryId (string or null) is required" }, { status: 400 });
  }

  const record = await setBlendBanner(code, user.sub, bannerMemoryId);
  if (!record) return NextResponse.json({ error: "not a member of this blend" }, { status: 403 });
  return NextResponse.json({ blend: await computeBlend(code) });
}
