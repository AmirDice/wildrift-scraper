/**
 * Access codes: beta invites, unlimited generations, and creator referrals.
 *
 * These are three uses of one mechanism. A code is a short string that arrives
 * as a link (wrtruemeta.com/i/CODE), grants whatever its record says it grants,
 * and counts how many people it brought. A beta invite grants early access to
 * the build tools; a sponsorship link grants nothing but is counted; a code can
 * do both.
 *
 * The grant travels in a cookie signed with AUTH_SECRET, so a visitor cannot
 * award themselves unlimited generations by editing it. The cookie holds only
 * the code and its grants -- the record in KV stays the source of truth, so
 * revoking a code takes effect on the next request.
 *
 * Codes are created from /api/admin/codes with ADMIN_TOKEN. There is no public
 * way to mint one.
 */
import crypto from "node:crypto";
import { cookies } from "next/headers";
import { kvGetJson, kvIncr, kvSetJson, kvGetNumbers, kvDelete } from "@/lib/kv";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

export const ACCESS_COOKIE = "wtm_access";
export const ACCESS_MAX_AGE = 60 * 60 * 24 * 180; // half a year

const AUTH_SECRET = process.env.AUTH_SECRET ?? "";

export type AccessKind = "beta" | "referral";

export interface AccessCode {
  code: string;
  kind: AccessKind;
  /** Who or what this code is for: "Beta wave 1", "YouTube: <channel>". */
  label: string;
  /** Early access to the build tools while they are still gated. */
  grantsBeta: boolean;
  /** Exempt from the daily generation cap. */
  unlimitedBuilds: boolean;
  createdAt: string;
  /** ISO date, or null to never expire. */
  expiresAt: string | null;
  /** Cap on activations, or null for unlimited. */
  maxUses: number | null;
  active: boolean;
}

/** What a visitor carrying a valid code is entitled to. */
export interface AccessGrant {
  code: string;
  label: string;
  kind: AccessKind;
  beta: boolean;
  unlimited: boolean;
}

const codeKey = (code: string) => `access:code:${code}`;
const INDEX_KEY = "access:index";
const clicksKey = (code: string) => `access:clicks:${code}`;
const activationsKey = (code: string) => `access:activations:${code}`;
const signInsKey = (code: string) => `access:signins:${code}`;

/** Human-typeable: no vowels (so it cannot spell anything) and no look-alikes. */
function newCode(prefix: string): string {
  const alphabet = "BCDFGHJKLMNPQRSTVWXZ23456789";
  const body = Array.from(crypto.randomBytes(7))
    .map((byte) => alphabet[byte % alphabet.length])
    .join("");
  return `${prefix}${body}`;
}

/* ── the signed cookie ───────────────────────────────────────────────────── */

function sign(payload: string): string {
  return crypto.createHmac("sha256", AUTH_SECRET).update(payload).digest("base64url");
}

export function signAccessCookie(grant: AccessGrant): string {
  const payload = Buffer.from(JSON.stringify(grant)).toString("base64url");
  return `${payload}.${sign(payload)}`;
}

export function readAccessCookie(value: string | undefined | null): AccessGrant | null {
  if (!value || !AUTH_SECRET) return null;
  const [payload, signature] = value.split(".");
  if (!payload || !signature) return null;
  const expected = sign(payload);
  if (
    expected.length !== signature.length
    || !crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature))
  ) {
    return null;
  }
  try {
    const grant = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as AccessGrant;
    return grant.code ? grant : null;
  } catch {
    return null;
  }
}

/* ── the records ─────────────────────────────────────────────────────────── */

export async function createCode(input: {
  kind: AccessKind;
  label: string;
  grantsBeta?: boolean;
  unlimitedBuilds?: boolean;
  expiresAt?: string | null;
  maxUses?: number | null;
}): Promise<AccessCode> {
  const record: AccessCode = {
    code: newCode(input.kind === "beta" ? "B" : "R"),
    kind: input.kind,
    label: input.label.trim().slice(0, 80) || "Untitled",
    // A beta invite defaults to granting beta; a referral link defaults to
    // granting nothing, because a sponsorship is about attribution, not access.
    grantsBeta: input.grantsBeta ?? input.kind === "beta",
    unlimitedBuilds: input.unlimitedBuilds ?? false,
    createdAt: new Date().toISOString(),
    expiresAt: input.expiresAt ?? null,
    maxUses: input.maxUses ?? null,
    active: true,
  };
  await kvSetJson(codeKey(record.code), record);
  const index = await kvGetJson<string[]>(INDEX_KEY, []);
  await kvSetJson(INDEX_KEY, [record.code, ...index].slice(0, 500));
  return record;
}

export async function getCode(code: string): Promise<AccessCode | null> {
  return kvGetJson<AccessCode | null>(codeKey(code.toUpperCase()), null);
}

export async function setCodeActive(code: string, active: boolean): Promise<AccessCode | null> {
  const record = await getCode(code);
  if (!record) return null;
  record.active = active;
  await kvSetJson(codeKey(record.code), record);
  return record;
}

export async function deleteCode(code: string): Promise<boolean> {
  const record = await getCode(code);
  if (!record) return false;
  await kvDelete(codeKey(record.code));
  const index = await kvGetJson<string[]>(INDEX_KEY, []);
  await kvSetJson(INDEX_KEY, index.filter((entry) => entry !== record.code));
  return true;
}

export interface CodeStats {
  clicks: number;
  activations: number;
  signIns: number;
}

export async function codeStats(code: string): Promise<CodeStats> {
  const [clicks, activations, signIns] = await kvGetNumbers([
    clicksKey(code), activationsKey(code), signInsKey(code),
  ]);
  return { clicks, activations, signIns };
}

export async function listCodes(): Promise<(AccessCode & CodeStats)[]> {
  const index = await kvGetJson<string[]>(INDEX_KEY, []);
  const records = await Promise.all(index.map((code) => getCode(code)));
  const live = records.filter((record): record is AccessCode => Boolean(record));
  const stats = await Promise.all(live.map((record) => codeStats(record.code)));
  return live.map((record, i) => ({ ...record, ...stats[i] }));
}

/** Whether a code can still be used, and why not when it cannot. */
export async function redeemable(record: AccessCode | null): Promise<{ ok: boolean; reason?: string }> {
  if (!record) return { ok: false, reason: "That invite link is not valid." };
  if (!record.active) return { ok: false, reason: "That invite link has been turned off." };
  if (record.expiresAt && Date.parse(record.expiresAt) < Date.now()) {
    return { ok: false, reason: "That invite link has expired." };
  }
  if (record.maxUses != null) {
    const { activations } = await codeStats(record.code);
    if (activations >= record.maxUses) return { ok: false, reason: "That invite link is fully claimed." };
  }
  return { ok: true };
}

export function grantFrom(record: AccessCode): AccessGrant {
  return {
    code: record.code,
    label: record.label,
    kind: record.kind,
    beta: record.grantsBeta,
    unlimited: record.unlimitedBuilds,
  };
}

/* ── server-side helpers ─────────────────────────────────────────────────── */

/** The grant the current request is carrying, if any. Server components only. */
export async function currentGrant(): Promise<AccessGrant | null> {
  const store = await cookies();
  return readAccessCookie(store.get(ACCESS_COOKIE)?.value);
}

/**
 * Whether the build tools should be reachable for this request: either they
 * have launched for everyone, or this visitor is holding a beta invite.
 *
 * Reading a cookie makes the calling page dynamic, which is the price of
 * per-visitor gating and is why the flag is still checked first: once the tools
 * launch, this short-circuits before touching cookies at all.
 */
export async function buildToolsVisible(): Promise<boolean> {
  if (BUILD_TOOLS_LIVE) return true;
  return Boolean((await currentGrant())?.beta);
}

export const countClick = (code: string) => kvIncr(clicksKey(code));
export const countActivation = (code: string) => kvIncr(activationsKey(code));
export const countSignIn = (code: string) => kvIncr(signInsKey(code));
