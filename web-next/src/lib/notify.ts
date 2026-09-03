import { KV_CONFIGURED, kvGet, kvList, kvPushCapped, kvSet, kvGetNumber, kvIncr } from "@/lib/kv";

/**
 * The notify list: who wants to hear when the numbers move or something ships.
 *
 * Two topics, because they are two different promises. A data refresh is
 * routine and frequent (every EU or NA collection, roughly fortnightly); a
 * feature is rare and worth an interruption. Someone who wants to know when
 * Hecarim's win rate is re-measured is not necessarily someone who wants an
 * email about the overlay, and bundling them is how a list gets unsubscribed
 * from. So the topics are stored per subscriber and mailed separately.
 *
 * Storage is deliberately dumb: one KV key per address holds the record, and a
 * capped log holds the same records in arrival order so the list can be read
 * back without scanning the keyspace. The per-address key is what makes a
 * second signup an update rather than a duplicate.
 *
 * No confirmation loop yet. Double opt-in is the right thing before the first
 * send goes out, and nothing here sends mail, so the honest state is "we hold
 * addresses that asked to be held" rather than "we run a mailing list".
 */

export const NOTIFY_TOPICS = ["data", "features"] as const;
export type NotifyTopic = (typeof NOTIFY_TOPICS)[number];

export interface NotifySubscriber {
  email: string;
  topics: NotifyTopic[];
  /** Which page the signup came from, so we learn what actually converts. */
  source: string;
  at: string;
}

const KEY = (email: string) => `notify:sub:${email}`;
const LOG = "notify:log";
const COUNT = "notify:count";

/** Cap on the readable log. The per-address keys are the real store; this is
 *  an ordered view for export, and 5000 is far more than the list will hold
 *  before it needs a real mail provider anyway. */
const LOG_CAP = 5000;

/**
 * Normalises an address, or returns null if it is not one.
 *
 * Deliberately permissive: one @, something either side, a dot in the domain,
 * no spaces. Anything stricter rejects valid addresses (plus-addressing, new
 * TLDs, unicode domains) and the only cost of a bad address here is a bounce
 * later. Lowercased so "A@b.com" and "a@b.com" are one subscriber.
 */
export function normaliseEmail(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const email = raw.trim().toLowerCase();
  if (email.length < 6 || email.length > 254) return null;
  if (/\s/.test(email)) return null;
  const at = email.indexOf("@");
  if (at < 1 || at !== email.lastIndexOf("@")) return null;
  const domain = email.slice(at + 1);
  if (domain.length < 3 || !domain.includes(".") || domain.startsWith(".") || domain.endsWith(".")) {
    return null;
  }
  return email;
}

/** Keeps only recognised topics, and defaults to both rather than none: an
 *  empty selection is a UI accident, not a request for silence. */
export function normaliseTopics(raw: unknown): NotifyTopic[] {
  const all = NOTIFY_TOPICS as readonly string[];
  const picked = Array.isArray(raw)
    ? raw.filter((t): t is NotifyTopic => typeof t === "string" && all.includes(t))
    : [];
  return picked.length ? Array.from(new Set(picked)) : [...NOTIFY_TOPICS];
}

export interface SubscribeResult {
  ok: boolean;
  /** True when this address was already on the list, so the UI can say so
   *  instead of implying a second signup did something. */
  existing: boolean;
  stored: boolean;
}

export async function subscribe(
  email: string,
  topics: NotifyTopic[],
  source: string,
): Promise<SubscribeResult> {
  // With no KV configured the form must not claim success. Saying "you're on
  // the list" when nothing was written is the one failure mode here that
  // actually costs something: the person stops checking back.
  if (!KV_CONFIGURED) return { ok: false, existing: false, stored: false };

  const prior = await kvGet(KEY(email));
  const record: NotifySubscriber = {
    email,
    topics,
    source: source.slice(0, 60),
    at: new Date().toISOString(),
  };
  const json = JSON.stringify(record);
  await kvSet(KEY(email), json);
  if (!prior) {
    await kvPushCapped(LOG, json, LOG_CAP);
    await kvIncr(COUNT);
  }
  return { ok: true, existing: Boolean(prior), stored: true };
}

export async function subscriberCount(): Promise<number> {
  return kvGetNumber(COUNT);
}

/** Newest first. Records that fail to parse are skipped rather than thrown:
 *  one bad row must not make the whole list unreadable. */
export async function subscribers(limit = 1000): Promise<NotifySubscriber[]> {
  const rows = await kvList(LOG, limit);
  const out: NotifySubscriber[] = [];
  for (const row of rows) {
    try {
      out.push(JSON.parse(row) as NotifySubscriber);
    } catch {
      continue;
    }
  }
  return out;
}
