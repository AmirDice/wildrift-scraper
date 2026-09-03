"use client";

import { useState } from "react";

/**
 * Join the notify list.
 *
 * Both topics are ticked by default. The alternative -- make people choose --
 * turns one decision into three and loses the ones who came to press a button,
 * and anyone who only wants one of the two can untick in a tap.
 *
 * The result line is honest about the three outcomes that are not "success":
 * a bad address, an address already on the list, and a storage failure. The
 * last one especially: a green tick over a dropped write is a promise that
 * silently will not be kept.
 */

type Topic = "data" | "features";
type State = "idle" | "sending" | "done" | "existing" | "error";

const TOPICS: { key: Topic; label: string; hint: string }[] = [
  { key: "data", label: "Data refreshes", hint: "when EU or NA win rates are re-collected" },
  { key: "features", label: "New features", hint: "the overlay, and whatever ships next" },
];

export function NotifyForm({ source, className = "" }: { source: string; className?: string }) {
  const [email, setEmail] = useState("");
  const [topics, setTopics] = useState<Topic[]>(["data", "features"]);
  const [state, setState] = useState<State>("idle");
  const [error, setError] = useState("");

  const toggle = (key: Topic) =>
    setTopics((prev) => (prev.includes(key) ? prev.filter((t) => t !== key) : [...prev, key]));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (state === "sending") return;
    setState("sending");
    setError("");
    try {
      const response = await fetch("/api/notify", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, topics, source }),
      });
      const data = (await response.json()) as { error?: string; existing?: boolean };
      if (!response.ok) {
        setError(data.error ?? "Something went wrong. Try again.");
        setState("error");
        return;
      }
      setState(data.existing ? "existing" : "done");
    } catch {
      setError("Could not reach the server. Try again.");
      setState("error");
    }
  }

  if (state === "done" || state === "existing") {
    return (
      <div className={`glass rounded-xl border border-emerald-400/30 p-4 ${className}`}>
        <p className="text-sm font-semibold text-emerald-300">
          {state === "existing" ? "You were already on the list." : "You are on the list."}
        </p>
        <p className="mt-1 text-xs text-muted">
          {state === "existing"
            ? "Your choices have been updated. Nothing else to do."
            : "One email when there is something to say, and nothing in between."}
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className={`glass rounded-xl border border-white/10 p-4 ${className}`}>
      <label htmlFor="notify-email" className="block text-sm font-semibold text-text">
        Get told when it lands
      </label>
      <p className="mt-1 text-xs text-muted">
        No account needed. One address, unsubscribed by replying.
      </p>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          id="notify-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          autoComplete="email"
          className="min-w-0 flex-1 rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-text outline-none transition placeholder:text-faint focus:border-accent/60"
        />
        <button
          type="submit"
          disabled={state === "sending"}
          className="shrink-0 rounded-lg bg-emerald-400 px-4 py-2 text-sm font-bold text-black transition hover:brightness-110 disabled:opacity-60"
        >
          {state === "sending" ? "Adding..." : "Notify me"}
        </button>
      </div>

      <fieldset className="mt-3">
        <legend className="sr-only">What to be notified about</legend>
        <div className="flex flex-col gap-1.5">
          {TOPICS.map((topic) => (
            <label key={topic.key} className="flex cursor-pointer items-start gap-2 text-xs">
              <input
                type="checkbox"
                checked={topics.includes(topic.key)}
                onChange={() => toggle(topic.key)}
                className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-emerald-400"
              />
              <span>
                <span className="font-medium text-text">{topic.label}</span>
                <span className="text-muted"> {topic.hint}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {state === "error" && (
        <p role="alert" className="mt-3 text-xs font-medium text-red-300">
          {error}
        </p>
      )}
    </form>
  );
}
