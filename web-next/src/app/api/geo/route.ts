import { NextResponse } from "next/server";
import { CONSENT_REGIONS } from "@/lib/analytics";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/geo -> { consentRequired }
 *
 * Whether this visitor is in a region where analytics cookies need consent
 * first (EU, EEA, UK, Switzerland), from Vercel's own IP-country header.
 * The pages are static, so they cannot know this themselves; the consent
 * banner asks here. Only the yes/no leaves the server, never the country.
 * An unknown country counts as requiring consent: asking someone who did
 * not need asking is harmless, the other way round is not.
 */
export function GET(request: Request) {
  const country = request.headers.get("x-vercel-ip-country")?.toUpperCase() ?? "";
  const consentRequired = !country || CONSENT_REGIONS.includes(country);
  return NextResponse.json({ consentRequired }, { headers: { "Cache-Control": "private, no-store" } });
}
