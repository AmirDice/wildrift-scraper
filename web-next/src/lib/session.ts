/**
 * Sign-in with Google, without an auth framework.
 *
 * The whole flow is three small pieces:
 *   1. The browser renders Google Identity Services and hands us an ID token
 *      (a signed JWT) -- see components/google-sign-in.tsx.
 *   2. verifyGoogleIdToken() checks that JWT's RS256 signature against Google's
 *      published JWKS, plus issuer / audience / expiry. No network round-trip
 *      per request: the key set is cached for an hour.
 *   3. We mint our own compact session cookie (HMAC-SHA256 over the payload)
 *      so later requests cost nothing to authenticate.
 *
 * Env required to actually enable sign-in:
 *   NEXT_PUBLIC_GOOGLE_CLIENT_ID  the OAuth client ID (public, used by GIS)
 *   AUTH_SECRET                   random string used to sign session cookies
 */
import crypto from "node:crypto";

export const SESSION_COOKIE = "wtm_session";
export const SESSION_MAX_AGE = 60 * 60 * 24 * 30; // 30 days

export const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";
const AUTH_SECRET = process.env.AUTH_SECRET ?? "";

/** Sign-in is only offered when both halves are configured. */
export const AUTH_CONFIGURED = Boolean(GOOGLE_CLIENT_ID && AUTH_SECRET);

/**
 * Accounts that are exempt from the daily generation cap.
 *
 * Comma-separated in ADMIN_EMAILS, deliberately NOT hard-coded: the repository
 * is public, and an owner's personal address does not belong in it. Compared
 * against the Google-verified email on the session, so it cannot be spoofed by
 * editing a cookie -- the session is HMAC-signed and the email inside it came
 * from a token checked against Google's JWKS.
 *
 * The access-code route to unlimited generations still exists and is unchanged.
 * This one is tied to the account rather than to a cookie, so it survives a
 * cleared browser and works on any device the owner signs in on.
 */
const ADMIN_EMAILS = new Set(
  (process.env.ADMIN_EMAILS ?? "")
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean),
);

export function isAdmin(user: { email?: string } | null | undefined): boolean {
  const email = user?.email?.trim().toLowerCase();
  return Boolean(email && ADMIN_EMAILS.has(email));
}

export interface SessionUser {
  /** Google subject id: the stable per-user key our quotas are counted against. */
  sub: string;
  email: string;
  name: string;
  picture: string;
  /** Issued-at, epoch seconds. */
  iat: number;
}

function b64urlEncode(input: Buffer | string): string {
  return Buffer.from(input).toString("base64url");
}

function b64urlDecode(input: string): string {
  return Buffer.from(input, "base64url").toString("utf8");
}

function hmac(payload: string): string {
  return crypto.createHmac("sha256", AUTH_SECRET).update(payload).digest("base64url");
}

/* ── our session cookie ──────────────────────────────────────────────────── */

export function signSession(user: Omit<SessionUser, "iat">): string {
  const payload = b64urlEncode(JSON.stringify({ ...user, iat: Math.floor(Date.now() / 1000) }));
  return `${payload}.${hmac(payload)}`;
}

export function readSession(cookieValue: string | undefined | null): SessionUser | null {
  if (!cookieValue || !AUTH_SECRET) return null;
  const [payload, signature] = cookieValue.split(".");
  if (!payload || !signature) return null;

  const expected = hmac(payload);
  // Constant-time compare; timingSafeEqual throws on length mismatch.
  if (
    expected.length !== signature.length ||
    !crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature))
  ) {
    return null;
  }
  try {
    const user = JSON.parse(b64urlDecode(payload)) as SessionUser;
    if (!user.sub) return null;
    if (Math.floor(Date.now() / 1000) - user.iat > SESSION_MAX_AGE) return null;
    return user;
  } catch {
    return null;
  }
}

/* ── Google ID token verification ────────────────────────────────────────── */

type Jwk = { kid: string; n: string; e: string; kty: string; alg?: string };
const JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs";
const JWKS_TTL_MS = 60 * 60 * 1000;
let jwksCache: { keys: Jwk[]; fetchedAt: number } | null = null;

async function googleKeys(): Promise<Jwk[]> {
  if (jwksCache && Date.now() - jwksCache.fetchedAt < JWKS_TTL_MS) return jwksCache.keys;
  const res = await fetch(JWKS_URL, { cache: "no-store" });
  if (!res.ok) throw new Error(`jwks ${res.status}`);
  const { keys } = (await res.json()) as { keys: Jwk[] };
  jwksCache = { keys, fetchedAt: Date.now() };
  return keys;
}

const VALID_ISSUERS = new Set(["accounts.google.com", "https://accounts.google.com"]);

export async function verifyGoogleIdToken(idToken: string): Promise<Omit<SessionUser, "iat"> | null> {
  if (!AUTH_CONFIGURED) return null;
  const [rawHeader, rawPayload, rawSignature] = idToken.split(".");
  if (!rawHeader || !rawPayload || !rawSignature) return null;

  let header: { kid?: string; alg?: string };
  try {
    header = JSON.parse(b64urlDecode(rawHeader));
  } catch {
    return null;
  }
  if (header.alg !== "RS256" || !header.kid) return null;

  let keys: Jwk[];
  try {
    keys = await googleKeys();
  } catch {
    return null;
  }
  const jwk = keys.find((key) => key.kid === header.kid);
  if (!jwk) return null;

  const publicKey = crypto.createPublicKey({ key: jwk as crypto.JsonWebKey, format: "jwk" });
  const signed = Buffer.from(`${rawHeader}.${rawPayload}`);
  const valid = crypto.verify(
    "RSA-SHA256",
    signed,
    publicKey,
    Buffer.from(rawSignature, "base64url"),
  );
  if (!valid) return null;

  let payload: {
    iss?: string; aud?: string; sub?: string; exp?: number;
    email?: string; email_verified?: boolean | string; name?: string; picture?: string;
  };
  try {
    payload = JSON.parse(b64urlDecode(rawPayload));
  } catch {
    return null;
  }

  if (!payload.sub) return null;
  if (!payload.iss || !VALID_ISSUERS.has(payload.iss)) return null;
  if (payload.aud !== GOOGLE_CLIENT_ID) return null;
  if (!payload.exp || payload.exp * 1000 < Date.now()) return null;

  return {
    sub: payload.sub,
    email: payload.email ?? "",
    name: payload.name ?? payload.email?.split("@")[0] ?? "Summoner",
    picture: payload.picture ?? "",
  };
}
