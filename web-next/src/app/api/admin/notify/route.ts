import { NextResponse } from "next/server";
import { KV_CONFIGURED } from "@/lib/kv";
import { subscriberCount, subscribers } from "@/lib/notify";

/**
 * GET /api/admin/notify?token=...  -- read the notify list back.
 *
 * A list you cannot export is not a list. Returns JSON by default and CSV with
 * &format=csv, which is what actually gets pasted into a mail provider.
 *
 * Guarded by ADMIN_TOKEN like the usage read-out, and closed rather than
 * public when no token is configured. This one holds email addresses, so the
 * default matters more here than anywhere else on the site.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const expected = process.env.ADMIN_TOKEN ?? "";
  const url = new URL(request.url);
  const provided = url.searchParams.get("token") ?? "";
  if (!expected || provided !== expected) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (!KV_CONFIGURED) {
    return NextResponse.json({ error: "no KV configured" }, { status: 503 });
  }

  const topic = url.searchParams.get("topic");
  const all = await subscribers(5000);
  const rows = topic ? all.filter((s) => s.topics.includes(topic as never)) : all;

  if (url.searchParams.get("format") === "csv") {
    const csv = ["email,topics,source,at"]
      .concat(rows.map((s) => `${s.email},"${s.topics.join(" ")}",${s.source},${s.at}`))
      .join("\n");
    return new NextResponse(csv, {
      headers: {
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": 'attachment; filename="notify-list.csv"',
      },
    });
  }

  return NextResponse.json({
    total: await subscriberCount(),
    returned: rows.length,
    subscribers: rows,
  });
}
