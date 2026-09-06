import { KV_CONFIGURED, kvDelete, kvGet, kvGetJson, kvList, kvRightPush, kvSet, kvSetJson } from "@/lib/kv";

/**
 * Invite codes for the overlay alpha.
 *
 * The problem this solves is not security, it is HEADCOUNT. The APK is a file
 * anyone can pass on, and every install that reaches the build endpoint spends
 * real generation credit, so an alpha that goes further than intended is
 * expensive before it is embarrassing. A code that binds to the first device
 * that redeems it makes the tester list a number the owner chose rather than a
 * number the internet chose.
 *
 * Bound to a DEVICE rather than to a person, because the overlay already
 * identifies itself by ANDROID_ID for quota and adding an account system for
 * an alpha would be a bigger change than the thing being tested. The trade is
 * explicit: a tester who reinstalls or changes phone needs a new code, or the
 * old one released.
 *
 * The gate is enforced SERVER side. The app asking for a code is a courtesy to
 * the tester; the API refusing an unknown device is what actually holds, and
 * it holds for a modified APK too.
 */

/** Codes look like WR-XXXX-XXXX: readable aloud, unambiguous in a chat. */
const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";     // no I, O, 0, 1

export interface AlphaCode {
  code: string;
  note: string;
  createdAt: string;
  device: string | null;
  redeemedAt: string | null;
}

const codeKey = (code: string) => `alpha:code:${code}`;
const deviceKey = (device: string) => `alpha:device:${device}`;

/**
 * What a tester gets a day, against 5 for the public.
 *
 * Five is about five games: an hour of testing, and then the thing being
 * tested stops working and the feedback is "it stopped working". Unlimited
 * would be cleaner signal but puts no ceiling on a leaked code, and the alpha
 * is asking whether the overlay works, not how much one person can generate.
 */
export const ALPHA_DAILY_BUILDS = 25;

/** Is the gate switched on at all? Off means the alpha is over. */
export const ALPHA_GATE = (process.env.ALPHA_GATE ?? "").toLowerCase() === "1"
  || (process.env.ALPHA_GATE ?? "").toLowerCase() === "true";

export function normaliseCode(raw: string | null | undefined): string {
  return String(raw ?? "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 16);
}

export function normaliseDevice(raw: string | null | undefined): string {
  return String(raw ?? "").replace(/[^A-Za-z0-9-]/g, "").slice(0, 64);
}

function randomCode(): string {
  const pick = () => ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
  const block = () => Array.from({ length: 4 }, pick).join("");
  return `WR${block()}${block()}`;
}

/** Mint `count` unused codes. Returns them in the form testers are given. */
export async function mintCodes(count: number, note = ""): Promise<AlphaCode[]> {
  const out: AlphaCode[] = [];
  for (let i = 0; i < count; i++) {
    const code = randomCode();
    // A collision would silently hand two testers the same code and let the
    // second one steal the first one's slot.
    if (await kvGet(codeKey(code))) { i--; continue; }
    const record: AlphaCode = {
      code, note, createdAt: new Date().toISOString(), device: null, redeemedAt: null,
    };
    await kvSetJson(codeKey(code), record);
    await kvRightPush("alpha:codes", code);
    out.push(record);
  }
  return out;
}

export type RedeemResult =
  | { ok: true; code: string; already: boolean }
  | { ok: false; reason: "no-store" | "unknown-code" | "code-taken" | "bad-request" };

/**
 * Bind a code to a device.
 *
 * Idempotent for the SAME device: a tester who reinstalls and re-enters their
 * own code gets in rather than being told it is used, which is otherwise the
 * most likely support message of the whole alpha.
 */
export async function redeem(rawCode: string, rawDevice: string): Promise<RedeemResult> {
  const code = normaliseCode(rawCode);
  const device = normaliseDevice(rawDevice);
  if (!code || !device) return { ok: false, reason: "bad-request" };
  if (!KV_CONFIGURED) return { ok: false, reason: "no-store" };

  const record = await kvGetJson<AlphaCode | null>(codeKey(code), null);
  if (!record) return { ok: false, reason: "unknown-code" };
  if (record.device && record.device !== device) return { ok: false, reason: "code-taken" };

  const already = record.device === device;
  if (!already) {
    record.device = device;
    record.redeemedAt = new Date().toISOString();
    await kvSetJson(codeKey(code), record);
  }
  // The device index is what the hot path reads, so it must not need the code.
  await kvSet(deviceKey(device), code);
  return { ok: true, code, already };
}

/**
 * May this device use the API?
 *
 * Deliberately fails OPEN when the gate is off or there is no KV: a missing
 * environment variable should not take the alpha down for everyone who already
 * has a working code. When the gate IS on and the store IS there, an unknown
 * device is refused.
 */
export async function deviceAllowed(rawDevice: string): Promise<boolean> {
  if (!ALPHA_GATE || !KV_CONFIGURED) return true;
  const device = normaliseDevice(rawDevice);
  if (!device) return false;
  return Boolean(await kvGet(deviceKey(device)));
}

/**
 * Is this device a REDEEMED tester, as opposed to merely allowed?
 *
 * deviceAllowed fails open when the gate is off, which is right for access and
 * wrong for allowance: with ALPHA_GATE unset it would hand the whole public the
 * tester's 25. This asks the register directly and answers no when there is
 * nothing in it.
 */
export async function isAlphaDevice(rawDevice: string): Promise<boolean> {
  if (!KV_CONFIGURED) return false;
  const device = normaliseDevice(rawDevice);
  if (!device) return false;
  return Boolean(await kvGet(deviceKey(device)));
}

/** Every code and what became of it, newest last. */
export async function listCodes(limit = 500): Promise<AlphaCode[]> {
  if (!KV_CONFIGURED) return [];
  const codes = await kvList("alpha:codes", limit);
  const out: AlphaCode[] = [];
  for (const code of codes) {
    const record = await kvGetJson<AlphaCode | null>(codeKey(code), null);
    if (record) out.push(record);
  }
  return out;
}

/**
 * Release a code so it can be handed to somebody else, or revoke a tester.
 *
 * Clears the device index too. Without that the old device keeps working: the
 * hot path reads the index, not the code.
 */
export async function releaseCode(rawCode: string): Promise<boolean> {
  const code = normaliseCode(rawCode);
  if (!code || !KV_CONFIGURED) return false;
  const record = await kvGetJson<AlphaCode | null>(codeKey(code), null);
  if (!record) return false;
  if (record.device) await kvDelete(deviceKey(record.device));
  record.device = null;
  record.redeemedAt = null;
  await kvSetJson(codeKey(code), record);
  return true;
}
