"use client";

import { useState } from "react";

const TOPICS = [
  { key: "data", label: "Wrong or missing data" },
  { key: "builds", label: "Build tools feedback" },
  { key: "business", label: "Business, creators or sponsorship" },
  { key: "other", label: "Something else" },
];

const FIELD = "w-full rounded-lg border border-line bg-[#0e1322] px-3 py-2 text-sm text-text outline-none focus:border-accent/60";

export function ContactForm() {
  const [topic, setTopic] = useState("data");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setState("sending");
    setError("");
    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, name, email, message, website }),
      });
      const data = (await response.json()) as { ok?: boolean; error?: string };
      if (!response.ok || !data.ok) throw new Error(data.error || "The message could not be sent.");
      setState("sent");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The message could not be sent.");
      setState("idle");
    }
  }

  if (state === "sent") {
    return (
      <div className="rounded-2xl border border-emerald-400/30 bg-emerald-400/[0.07] p-5">
        <p className="font-semibold text-emerald-300">Message sent.</p>
        <p className="mt-1 text-sm text-muted">
          Thanks. {email ? "If it needs an answer, the reply will go to the address you gave." : "You did not leave an email, so we cannot reply, but every message is read."}
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-text">What is it about?</span>
        <select value={topic} onChange={(e) => setTopic(e.target.value)} className={FIELD}>
          {TOPICS.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
        </select>
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-text">Name <span className="font-normal text-faint">(optional)</span></span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-text">Email <span className="font-normal text-faint">(only if you want a reply)</span></span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={200} className={FIELD} />
        </label>
      </div>
      {/* Hidden from people, filled in by form bots. */}
      <input type="text" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)}
        aria-hidden="true" className="absolute left-[-9999px] h-0 w-0 opacity-0" name="website" />
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-text">Message</span>
        <textarea value={message} onChange={(e) => setMessage(e.target.value)} required minLength={10} maxLength={4000}
          rows={6} className={FIELD} placeholder="For a data problem, name the champion, the page and what looks wrong." />
      </label>
      {error && <p className="rounded-lg border border-bad/25 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</p>}
      <div>
        <button type="submit" disabled={state === "sending"}
          className="rounded-lg bg-accent px-5 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-50">
          {state === "sending" ? "Sending..." : "Send message"}
        </button>
      </div>
    </form>
  );
}
