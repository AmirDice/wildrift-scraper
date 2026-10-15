"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useAccount } from "@/components/account-provider";
import type { AgentAction, AgentAnswer, AgentQuotaState } from "@/lib/agent-types";
import { track } from "@/components/share-build";
import { SIGNED_IN_DAILY_AGENT_QUESTIONS } from "@/lib/agent-quota-limits";
import { agentSuggestions, championPrompts } from "@/lib/agent-suggestions";

type NavChampion = { name: string; slug: string; icon?: string };
type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  source?: AgentAnswer["source"];
  evidence?: string[];
  actions?: AgentAction[];
  followUps?: string[];
  error?: boolean;
};

type AgentContextValue = {
  open: boolean;
  openAgent: () => void;
  closeAgent: () => void;
  ask: (question: string) => void;
};

const AgentContext = createContext<AgentContextValue | null>(null);
// v2 drops the early beta conversation whose generic tier-list answers were
// under-grounded; users should not keep seeing those stale replies after the
// data layer is corrected.
const STORAGE_KEY = "wtm:site-agent:v2";

function freshId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function quotaLabel(quota: AgentQuotaState | null): string {
  if (!quota) return "Site-data answers are unlimited";
  if (quota.unlimited) return "Unlimited AI questions";
  return `${quota.remaining ?? 0} of ${quota.limit ?? 0} AI questions left today`;
}

export function SiteAgentProvider({
  children,
  champions,
}: {
  children: React.ReactNode;
  champions: NavChampion[];
}) {
  const pathname = usePathname();
  const { user, authConfigured } = useAccount();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [quota, setQuota] = useState<AgentQuotaState | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const championSlug = pathname.match(/^\/champions\/([^/?#]+)/)?.[1] ?? "";
  const champion = champions.find((entry) => entry.slug === championSlug);
  const contextualSuggestions = useMemo(
    () => agentSuggestions(pathname, champion?.name),
    [pathname, champion?.name],
  );

  useEffect(() => {
    try {
      const parsed = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]") as Message[];
      if (Array.isArray(parsed)) setMessages(parsed.slice(-14));
    } catch { /* ignore a stale local value */ }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-14))); } catch { /* storage disabled */ }
  }, [messages, hydrated]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    if (window.matchMedia("(max-width: 767px)").matches) document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    const timer = window.setTimeout(() => inputRef.current?.focus(), 120);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
      window.clearTimeout(timer);
    };
  }, [open]);

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading, open]);

  const refreshQuota = useCallback(async () => {
    try {
      const response = await fetch("/api/agent", { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json() as { quota?: AgentQuotaState };
      if (data.quota) setQuota(data.quota);
    } catch { /* the panel still works for deterministic answers */ }
  }, []);

  const openAgent = useCallback(() => {
    setOpen(true);
    track("agent_opened");
    void refreshQuota();
  }, [refreshQuota]);

  const closeAgent = useCallback(() => setOpen(false), []);

  const sendQuestion = useCallback(async (raw: string) => {
    const question = raw.trim().slice(0, 500);
    if (!question || loading) return;
    setOpen(true);
    setInput("");
    const history = messages.slice(-6).map(({ role, content }) => ({ role, content }));
    setMessages((current) => [...current, { id: freshId(), role: "user", content: question }]);
    setLoading(true);
    try {
      const response = await fetch("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, pathname, championSlug, history }),
      });
      const data = await response.json() as AgentAnswer & { error?: string };
      if (data.quota) setQuota(data.quota);
      if (!response.ok || !data.answer) {
        setMessages((current) => [...current, {
          id: freshId(),
          role: "assistant",
          content: data.error || "I couldn't answer that right now. Please try again.",
          error: true,
        }]);
        return;
      }
      setMessages((current) => [...current, {
        id: freshId(),
        role: "assistant",
        content: data.answer,
        source: data.source,
        evidence: data.evidence,
        actions: data.actions,
        followUps: data.followUps,
      }]);
    } catch {
      setMessages((current) => [...current, {
        id: freshId(), role: "assistant", error: true,
        content: "I couldn't reach the WRTrueMeta agent. Please try again.",
      }]);
    } finally {
      setLoading(false);
    }
  }, [championSlug, loading, messages, pathname]);

  const ask = useCallback((question: string) => {
    if (!open) track("agent_opened");
    void sendQuestion(question);
  }, [open, sendQuestion]);

  const value = useMemo(() => ({ open, openAgent, closeAgent, ask }), [open, openAgent, closeAgent, ask]);

  return (
    <AgentContext.Provider value={value}>
      {children}

      <button
        type="button"
        onClick={openAgent}
        aria-label="Ask WRTrueMeta"
        aria-expanded={open}
        tabIndex={open ? -1 : 0}
        className={`agent-launcher fixed right-3 z-[65] flex items-center gap-1.5 rounded-full border px-2.5 py-2 text-xs font-bold shadow-[0_14px_42px_rgba(0,0,0,.38)] backdrop-blur-xl transition hover:border-accent/60 hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent sm:right-4 ${open ? "pointer-events-none opacity-0" : "border-white/15 bg-[#101c2b]/90 text-text"}`}
      >
        <AgentSpark className="h-4 w-4 text-accent" />
        <span className="hidden sm:inline">Ask WRTrueMeta</span>
      </button>

      <div
        aria-hidden={!open}
        onMouseDown={(event) => { if (event.target === event.currentTarget) closeAgent(); }}
        className={`fixed inset-0 z-[90] bg-black/30 transition-opacity duration-300 md:bg-black/15 ${open ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"}`}
      >
        <aside
          role="dialog"
          aria-modal="true"
          aria-label="WRTrueMeta Agent"
          inert={!open}
          className={`absolute inset-y-0 right-0 flex w-full max-w-[31rem] flex-col border-l border-white/10 bg-[#08111f]/95 shadow-[-30px_0_90px_rgba(0,0,0,.55)] backdrop-blur-2xl transition-transform duration-300 ${open ? "translate-x-0" : "translate-x-full"}`}
        >
          <header className="relative overflow-hidden border-b border-white/10 px-5 pb-4 pt-[max(1rem,env(safe-area-inset-top))]">
            <div aria-hidden className="absolute inset-0 bg-[radial-gradient(circle_at_18%_0%,rgba(71,180,255,.18),transparent_48%)]" />
            <div className="relative flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-2xl border border-accent/25 bg-accent/10 shadow-[0_0_28px_rgba(70,180,255,.13)]">
                  <AgentSpark className="h-5 w-5 text-accent" />
                </span>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="font-semibold tracking-[0.08em]">WRTrueMeta Agent</h2>
                    <span className="rounded border border-accent/30 bg-accent/10 px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wider text-accent">Beta</span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted">Grounded in the page you are viewing</p>
                </div>
              </div>
              <button type="button" onClick={closeAgent} aria-label="Close agent" className="grid h-9 w-9 place-items-center rounded-full border border-white/10 text-muted transition hover:bg-white/[0.06] hover:text-text">
                <CloseIcon />
              </button>
            </div>
          </header>

          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-5">
            {messages.length === 0 ? (
              <div className="flex min-h-full flex-col justify-between gap-8">
                <div>
                  <div className="rounded-[1.4rem] border border-white/10 bg-white/[0.035] p-5">
                    <p className="text-[0.64rem] font-bold uppercase tracking-[0.18em] text-accent">Ask from this page</p>
                    <h3 className="mt-2 text-xl font-semibold">{champion ? `Understand ${champion.name} faster` : "Turn the data into an answer"}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-muted">Current stats, builds, players, matchups and patch history answer instantly. Open-ended analysis uses your AI allowance.</p>
                  </div>
                  <div className="mt-5 space-y-2">
                    {contextualSuggestions.map((prompt) => (
                      <button key={prompt} type="button" onClick={() => void sendQuestion(prompt)} className="group flex w-full items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.025] px-4 py-3 text-left text-sm transition hover:border-accent/35 hover:bg-accent/[0.055]">
                        <span>{prompt}</span><span className="text-accent transition group-hover:translate-x-0.5">→</span>
                      </button>
                    ))}
                  </div>
                </div>
                <p className="text-center text-xs text-faint">{quotaLabel(quota)}</p>
              </div>
            ) : (
              <div className="space-y-5">
                {messages.map((message) => (
                  <AgentMessage key={message.id} message={message} onFollowUp={sendQuestion} />
                ))}
                {loading && <AgentThinking />}
              </div>
            )}
          </div>

          <footer className="border-t border-white/10 bg-[#08111f]/90 p-4 pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur-xl sm:p-5">
            {messages.length > 0 && <p className="mb-2 text-right text-[0.68rem] text-faint">{quotaLabel(quota)}</p>}
            <form onSubmit={(event) => { event.preventDefault(); void sendQuestion(input); }} className="flex items-end gap-2 rounded-2xl border border-white/12 bg-white/[0.045] p-2 shadow-inner focus-within:border-accent/45">
              <input
                ref={inputRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                maxLength={500}
                placeholder={loading ? "Working through the site data…" : "Ask about this page…"}
                disabled={loading}
                className="min-h-10 flex-1 bg-transparent px-2 text-sm text-text outline-none placeholder:text-faint disabled:opacity-60"
              />
              <button type="submit" disabled={loading || !input.trim()} aria-label="Send question" className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent text-[#06111d] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-35">
                <SendIcon />
              </button>
            </form>
            {!user && authConfigured && quota?.canUnlockBySigningIn && (
              <p className="mt-2 text-center text-xs text-muted">Sign in from the account menu for {SIGNED_IN_DAILY_AGENT_QUESTIONS} AI questions per day.</p>
            )}
          </footer>
        </aside>
      </div>
    </AgentContext.Provider>
  );
}

function AgentMessage({ message, onFollowUp }: { message: Message; onFollowUp: (question: string) => void }) {
  const [rated, setRated] = useState(false);
  if (message.role === "user") {
    return <div className="ml-auto max-w-[88%] rounded-2xl rounded-tr-md border border-white/10 bg-white/[0.075] px-4 py-3 text-sm leading-relaxed">{message.content}</div>;
  }
  return (
    <div className="space-y-3">
      <div className={`rounded-[1.35rem] rounded-tl-md border p-4 ${message.error ? "border-rose-400/25 bg-rose-400/[0.06]" : "border-white/10 bg-white/[0.035]"}`}>
        {message.source && (
          <div className="mb-3 flex items-center gap-2 text-[0.62rem] font-bold uppercase tracking-[0.14em]">
            <span className={`h-1.5 w-1.5 rounded-full ${message.source === "data" ? "bg-emerald-300" : "bg-accent"}`} />
            <span className={message.source === "data" ? "text-emerald-300" : "text-accent"}>{message.source === "data" ? "WRTrueMeta data" : "AI analysis"}</span>
          </div>
        )}
        <p className="whitespace-pre-line text-sm leading-7 text-[#e8eef8]">{message.content}</p>
        {message.evidence && message.evidence.length > 0 && (
          <div className="mt-4 border-t border-white/8 pt-3">
            <p className="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-faint">Used for this answer</p>
            <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-muted">
              {message.evidence.map((fact, index) => <li key={`${fact}-${index}`} className="flex gap-2"><span className="text-accent">•</span><span>{fact}</span></li>)}
            </ul>
          </div>
        )}
      </div>
      {message.actions && message.actions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {message.actions.map((item) => <Link key={`${item.href}-${item.label}`} href={item.href} className="rounded-full border border-accent/25 bg-accent/[0.07] px-3 py-1.5 text-xs font-semibold text-accent transition hover:bg-accent/[0.13]">{item.label} →</Link>)}
        </div>
      )}
      {!message.error && (
        <div className="flex items-center gap-1 text-faint">
          <span className="mr-1 text-[0.65rem]">Helpful?</span>
          {["Yes", "No"].map((label) => <button key={label} type="button" disabled={rated} onClick={() => {
            setRated(true);
            const path = message.source === "model" ? "model" : "data";
            track(label === "Yes" ? `agent_feedback_yes_${path}` : `agent_feedback_no_${path}`);
          }} className="rounded-md px-2 py-1 text-[0.65rem] transition hover:bg-white/[0.06] hover:text-text disabled:opacity-40">{rated ? "Thanks" : label}</button>)}
        </div>
      )}
      {message.followUps && message.followUps.length > 0 && (
        <div className="flex flex-wrap gap-2 pt-1">
          {message.followUps.map((prompt) => <button key={prompt} type="button" onClick={() => onFollowUp(prompt)} className="rounded-full border border-white/10 bg-white/[0.025] px-3 py-1.5 text-left text-xs text-muted transition hover:border-accent/30 hover:text-text">{prompt}</button>)}
        </div>
      )}
    </div>
  );
}

function AgentThinking() {
  return (
    <div className="rounded-[1.35rem] rounded-tl-md border border-white/10 bg-white/[0.035] p-4">
      <div className="flex items-center gap-3">
        <span className="relative flex h-8 w-8 items-center justify-center rounded-xl bg-accent/10"><AgentSpark className="h-4 w-4 animate-pulse text-accent" /></span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3 text-xs"><span className="font-semibold text-text">Reading this page's data</span><span className="text-faint">Analyzing</span></div>
          <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.07]"><span className="block h-full w-2/3 animate-pulse rounded-full bg-gradient-to-r from-accent/40 to-accent" /></div>
        </div>
      </div>
    </div>
  );
}

/**
 * The site agent, for any component that wants to put a question to it.
 * Null outside the provider (it wraps the whole app in layout.tsx), so a
 * caller renders nothing rather than a button that does nothing.
 */
export function useSiteAgent(): AgentContextValue | null {
  return useContext(AgentContext);
}

/**
 * An inline "ask the agent" button, placed beside the data it asks about.
 *
 * Pass a question the fast path answers from site data where you can: a
 * question that reaches the model spends an anonymous visitor's one AI answer
 * for the day, and a button is easy to click without thinking about that.
 */
export function AskAgent({ question, label, className = "", compact = false }: { question: string; label?: string; className?: string; compact?: boolean }) {
  const agent = useContext(AgentContext);
  if (!agent) return null;
  // Icon-only, for cells too narrow for a sentence (the tier list's labels).
  if (compact) {
    return (
      <button
        type="button"
        onClick={() => agent.ask(question)}
        aria-label={label ?? question}
        title={label ?? question}
        className={`grid h-6 w-6 place-items-center rounded-full bg-black/25 text-white/80 transition hover:bg-black/40 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-white ${className}`}
      >
        <AgentSpark className="h-3.5 w-3.5" />
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={() => agent.ask(question)}
      className={`inline-flex items-center gap-1.5 rounded-full border border-accent/25 bg-accent/[0.06] px-3 py-1.5 text-left text-xs font-semibold text-accent transition hover:border-accent/45 hover:bg-accent/[0.12] focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent ${className}`}
    >
      <AgentSpark className="h-3.5 w-3.5 shrink-0" />
      {label ?? question}
    </button>
  );
}

export function AgentPromptChips({ champion }: { champion: string }) {
  const agent = useContext(AgentContext);
  if (!agent) return null;
  const prompts = championPrompts(champion);
  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-4 sm:px-6" aria-label={`Ask about ${champion}`}>
      <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {prompts.map((prompt) => (
          <button key={prompt} type="button" onClick={() => agent.ask(prompt)} className="group flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-[#0d1a2a]/75 px-3.5 py-2 text-xs font-semibold text-muted shadow-lg backdrop-blur-xl transition hover:border-accent/35 hover:text-text">
            <AgentSpark className="h-3.5 w-3.5 text-accent" />{prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function AgentSpark({ className = "" }: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden><path d="M12 2.8c.55 4.55 3.1 7.1 7.65 7.65-4.55.55-7.1 3.1-7.65 7.65-.55-4.55-3.1-7.1-7.65-7.65C8.9 9.9 11.45 7.35 12 2.8Z" fill="currentColor"/><path d="M19.1 15.5c.22 1.82 1.24 2.84 3.06 3.06-1.82.22-2.84 1.24-3.06 3.06-.22-1.82-1.24-2.84-3.06-3.06 1.82-.22 2.84-1.24 3.06-3.06Z" fill="currentColor" opacity=".65"/></svg>;
}

function CloseIcon() {
  return <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden><path d="m6 6 12 12M18 6 6 18" /></svg>;
}

function SendIcon() {
  return <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="m5 12 14-7-4 14-3-6-7-1Z"/><path d="m12 13 7-8"/></svg>;
}

