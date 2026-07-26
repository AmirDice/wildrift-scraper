"use client";

import { useState } from "react";
import { reasonsFor, type FeedbackVerdict } from "@/lib/feedback-options";

function ThumbIcon({ down = false }: { down?: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden
      style={down ? { transform: "rotate(180deg)" } : undefined}>
      <path d="M7 22V11" />
      <path d="M11 5.5 10.2 9a1 1 0 0 0 1 1.2h5.4a2 2 0 0 1 1.95 2.44l-1.1 5A2 2 0 0 1 15.5 19H7V11l2.6-6.2A1.6 1.6 0 0 1 11 4a1.4 1.4 0 0 1 1 1.5Z" />
    </svg>
  );
}

/**
 * "Was this build helpful?" on generated builds.
 *
 * A verdict alone is a weak signal, so picking one opens a short list of
 * reasons (fixed keys, so they aggregate) plus a free-text box. Everything is
 * optional: the verdict is already recorded by the time the reasons appear.
 */
export function BuildFeedback({ champion, className = "" }: { champion?: string; className?: string }) {
  const [verdict, setVerdict] = useState<FeedbackVerdict | null>(null);
  const [reasons, setReasons] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);

  const send = async (next: FeedbackVerdict, withDetail: boolean) => {
    try {
      await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          verdict: next,
          reasons: withDetail ? reasons : [],
          note: withDetail ? note : "",
          champion,
        }),
      });
    } catch {
      /* feedback is best-effort; never surface a failure here */
    }
  };

  const choose = (next: FeedbackVerdict) => {
    setVerdict(next);
    setReasons([]);
    void send(next, false);
  };

  const toggleReason = (key: string) => {
    setReasons((current) =>
      current.includes(key) ? current.filter((entry) => entry !== key) : [...current, key],
    );
  };

  if (sent) {
    return (
      <div className={`glass rounded-2xl p-4 ${className}`}>
        <p className="text-sm text-muted">Thanks. That goes straight into how the next builds get tuned.</p>
      </div>
    );
  }

  return (
    <div className={`glass rounded-2xl p-4 ${className}`}>
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Was this build helpful?</p>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => choose("up")}
            aria-pressed={verdict === "up"}
            title="This build was helpful"
            className={`grid h-8 w-8 place-items-center rounded-lg border transition ${
              verdict === "up"
                ? "border-emerald-400/50 bg-emerald-400/15 text-emerald-300"
                : "border-line text-muted hover:border-emerald-400/40 hover:text-emerald-300"
            }`}
          >
            <ThumbIcon />
          </button>
          <button
            onClick={() => choose("down")}
            aria-pressed={verdict === "down"}
            title="This build missed"
            className={`grid h-8 w-8 place-items-center rounded-lg border transition ${
              verdict === "down"
                ? "border-rose-400/50 bg-rose-400/15 text-rose-300"
                : "border-line text-muted hover:border-rose-400/40 hover:text-rose-300"
            }`}
          >
            <ThumbIcon down />
          </button>
        </div>
      </div>

      {verdict && (
        <div className="mt-3 border-t border-line/60 pt-3">
          <p className="text-xs text-muted">
            {verdict === "up" ? "What worked?" : "What was wrong with it?"}{" "}
            <span className="text-faint">Optional.</span>
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {reasonsFor(verdict).map((reason) => (
              <button
                key={reason.key}
                onClick={() => toggleReason(reason.key)}
                className={`rounded-full px-2.5 py-1 text-xs font-medium transition ${
                  reasons.includes(reason.key)
                    ? "bg-accent/20 text-accent"
                    : "bg-white/[0.05] text-muted hover:text-text"
                }`}
              >
                {reason.label}
              </button>
            ))}
          </div>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={2}
            maxLength={500}
            placeholder="Anything else? What would you have built instead?"
            className="mt-2 w-full resize-y rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none placeholder:text-faint focus:border-accent/50"
          />
          <button
            onClick={async () => {
              await send(verdict, true);
              setSent(true);
            }}
            className="mt-2 rounded-lg bg-accent/20 px-3 py-1.5 text-xs font-bold text-accent transition hover:bg-accent/30"
          >
            Send feedback
          </button>
        </div>
      )}
    </div>
  );
}
