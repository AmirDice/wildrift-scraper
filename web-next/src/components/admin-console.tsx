"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui";

interface AccessCodeRow {
  code: string;
  kind: "beta" | "referral";
  label: string;
  grantsBeta: boolean;
  unlimitedBuilds: boolean;
  active: boolean;
  maxUses: number | null;
  createdAt: string;
  clicks: number;
  activations: number;
  signIns: number;
}

interface BestBuildRow {
  championSlug: string;
  player: string;
  standing?: string;
  items: string[];
  boots?: string;
  runes: string[];
  note?: string;
  updatedAt: string;
}

interface CreatorAdminRow {
  id: string;
  name: string;
  tagline: string;
  categories: string[];
  languages?: string[];
  links: Record<string, string>;
  avatar?: string;
  lastChecked: string;
  updatedAt: string;
}

const CREATOR_CATEGORIES = [
  ["educational", "Educational"], ["guides", "Guides & builds"], ["high-elo", "High elo"],
  ["funny", "Funny"], ["montage", "Montages"], ["esports", "Esports"],
  ["news", "News & patches"], ["community", "Community"],
] as const;
const CREATOR_PLATFORMS = ["youtube", "twitch", "tiktok", "kick", "x", "instagram", "discord", "website"] as const;

const TOKEN_KEY = "wtm_admin_token";

/**
 * The admin console: invite links and hand-recorded best-player builds.
 *
 * The token lives in sessionStorage rather than a cookie or the URL, so it is
 * gone when the tab closes and never ends up in a shared link or a server log.
 * Everything it can do is already gated server-side; this is only the keyboard.
 */
export function AdminConsole() {
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = sessionStorage.getItem(TOKEN_KEY);
        if (saved) {
          setToken(saved);
          setReady(true);
        }
      } catch {
        /* ignore */
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const unlock = async () => {
    setError(null);
    try {
      const res = await fetch(`/api/admin/codes?token=${encodeURIComponent(token)}`);
      if (!res.ok) {
        setError("That token was rejected.");
        return;
      }
      try {
        sessionStorage.setItem(TOKEN_KEY, token);
      } catch {
        /* ignore */
      }
      setReady(true);
    } catch {
      setError("Could not reach the server.");
    }
  };

  if (!ready) {
    return (
      <Card className="mx-auto max-w-md p-6">
        <h2 className="font-semibold">Admin token</h2>
        <p className="mt-1 text-sm text-muted">
          The value of <code className="text-text">ADMIN_TOKEN</code>. Kept in this tab only.
        </p>
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && void unlock()}
          className="mt-3 w-full rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
        />
        <button
          onClick={unlock}
          disabled={!token.trim()}
          className="mt-3 w-full rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
        >
          Unlock
        </button>
        {error && <p className="mt-2 text-xs text-bad">{error}</p>}
      </Card>
    );
  }

  return (
    <div className="space-y-8">
      <CodesPanel token={token} />
      <BestBuildsPanel token={token} />
      <CreatorsPanel token={token} />
    </div>
  );
}

function CreatorsPanel({ token }: { token: string }) {
  const emptyForm = {
    id: "", name: "", tagline: "", categories: [] as string[], languages: "", avatar: "",
    lastChecked: "", links: Object.fromEntries(CREATOR_PLATFORMS.map((platform) => [platform, ""])) as Record<string, string>,
  };
  const [creators, setCreators] = useState<CreatorAdminRow[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`/api/admin/creators?token=${encodeURIComponent(token)}`);
    if (!res.ok) return;
    const data = await res.json() as { creators: CreatorAdminRow[] };
    setCreators(data.creators);
  }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const setField = (key: "name" | "tagline" | "languages" | "avatar" | "lastChecked", value: string) =>
    setForm((current) => ({ ...current, [key]: value }));
  const toggleCategory = (category: string) => setForm((current) => ({
    ...current,
    categories: current.categories.includes(category)
      ? current.categories.filter((entry) => entry !== category)
      : [...current.categories, category],
  }));

  const save = async () => {
    if (!form.name.trim() || !form.tagline.trim() || busy) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch(`/api/admin/creators?token=${encodeURIComponent(token)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          languages: form.languages.split(",").map((entry) => entry.trim()).filter(Boolean),
        }),
      });
      const data = await res.json() as { creator?: CreatorAdminRow; error?: string };
      setNote(res.ok ? `Saved ${data.creator?.name ?? form.name}.` : data.error ?? "Could not save creator.");
      if (res.ok) {
        setForm(emptyForm);
        await load();
      }
    } finally {
      setBusy(false);
    }
  };

  const edit = (creator: CreatorAdminRow) => {
    setForm({
      id: creator.id,
      name: creator.name,
      tagline: creator.tagline,
      categories: [...creator.categories],
      languages: creator.languages?.join(", ") ?? "",
      avatar: creator.avatar ?? "",
      lastChecked: creator.lastChecked,
      links: Object.fromEntries(CREATOR_PLATFORMS.map((platform) => [platform, creator.links[platform] ?? ""])),
    });
    setNote(`Editing ${creator.name}.`);
  };

  const inputClass = "w-full rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50";
  return (
    <section>
      <h2 className="text-xl font-semibold tracking-tight">Content creators</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Add or update verified creators shown in the public creator directory. Include at least one category
        and one full platform URL. The verification date defaults to today when left blank.
      </p>

      <Card className="mt-4 p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">
            Name
            <input value={form.name} onChange={(event) => setField("name", event.target.value)} placeholder="Creator or channel name" className={`mt-1 ${inputClass}`} />
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">
            Tagline
            <input value={form.tagline} onChange={(event) => setField("tagline", event.target.value)} placeholder="What their content is known for" className={`mt-1 ${inputClass}`} />
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">
            Languages
            <input value={form.languages} onChange={(event) => setField("languages", event.target.value)} placeholder="English, Spanish" className={`mt-1 ${inputClass}`} />
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">
            Last checked
            <input type="date" value={form.lastChecked} onChange={(event) => setField("lastChecked", event.target.value)} className={`mt-1 ${inputClass}`} />
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint sm:col-span-2">
            Avatar URL (optional)
            <input value={form.avatar} onChange={(event) => setField("avatar", event.target.value)} placeholder="https://…" className={`mt-1 ${inputClass}`} />
          </label>
        </div>

        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-faint">Categories</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {CREATOR_CATEGORIES.map(([key, label]) => (
              <button key={key} type="button" onClick={() => toggleCategory(key)} className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${form.categories.includes(key) ? "bg-accent text-black" : "border border-line text-muted hover:text-text"}`}>
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {CREATOR_PLATFORMS.map((platform) => (
            <label key={platform} className="text-xs font-semibold uppercase tracking-wide text-faint">
              {platform}
              <input
                value={form.links[platform]}
                onChange={(event) => setForm((current) => ({ ...current, links: { ...current.links, [platform]: event.target.value } }))}
                placeholder={`https://${platform === "x" ? "x.com" : `${platform}.com`}/…`}
                className={`mt-1 ${inputClass}`}
              />
            </label>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button type="button" onClick={save} disabled={!form.name.trim() || !form.tagline.trim() || busy} className="rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40">
            {form.id ? "Update creator" : "Add creator"}
          </button>
          {form.id && (
            <button type="button" onClick={() => { setForm(emptyForm); setNote(null); }} className="rounded-lg border border-line px-4 py-2 text-sm text-muted transition hover:text-text">
              Cancel edit
            </button>
          )}
          {note && <p className="text-xs text-accent">{note}</p>}
        </div>
      </Card>

      <div className="mt-4 divide-y divide-line/60">
        {creators.map((creator) => (
          <div key={creator.id} className="flex flex-wrap items-center gap-3 py-3">
            <span className="min-w-40 flex-1 font-medium">{creator.name}</span>
            <span className="text-xs text-faint">{creator.categories.join(" · ")}</span>
            <span className="text-xs text-muted">Checked {creator.lastChecked}</span>
            <button type="button" onClick={() => edit(creator)} className="rounded-md border border-line px-3 py-1 text-xs text-muted transition hover:text-text">Edit</button>
          </div>
        ))}
        {creators.length === 0 && <p className="py-6 text-center text-sm text-faint">No creators added in Admin yet.</p>}
      </div>
    </section>
  );
}

function CodesPanel({ token }: { token: string }) {
  const [codes, setCodes] = useState<AccessCodeRow[]>([]);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<"beta" | "referral">("beta");
  const [unlimited, setUnlimited] = useState(true);
  const [maxUses, setMaxUses] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`/api/admin/codes?token=${encodeURIComponent(token)}`);
    if (!res.ok) return;
    const data = (await res.json()) as { codes: AccessCodeRow[] };
    setCodes(data.codes);
  }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const create = async () => {
    if (!label.trim() || busy) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch(`/api/admin/codes?token=${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          label,
          unlimitedBuilds: unlimited,
          maxUses: maxUses ? Number(maxUses) : null,
        }),
      });
      const data = (await res.json()) as { url?: string; error?: string };
      setNote(res.ok ? `Created: ${data.url}` : data.error ?? "Could not create that code.");
      if (res.ok) {
        setLabel("");
        await load();
      }
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (code: string, active: boolean) => {
    await fetch(`/api/admin/codes?token=${encodeURIComponent(token)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, active }),
    });
    await load();
  };

  return (
    <section>
      <h2 className="text-xl font-semibold tracking-tight">Invite &amp; referral links</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        A <span className="text-text">beta</span> link opens the build tools before launch. A{" "}
        <span className="text-text">referral</span> link grants nothing but counts the traffic it sends,
        which is what a sponsored creator needs. Either can carry unlimited generations.
      </p>

      <Card className="mt-4 p-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-52 flex-1">
            <label className="mb-1 block text-[0.65rem] font-bold uppercase tracking-wide text-faint">
              Label
            </label>
            <input
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Beta wave 1, or a creator's name"
              className="w-full rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
            />
          </div>
          <div>
            <label className="mb-1 block text-[0.65rem] font-bold uppercase tracking-wide text-faint">Kind</label>
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value as "beta" | "referral")}
              className="rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none"
            >
              <option value="beta">Beta access</option>
              <option value="referral">Referral only</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[0.65rem] font-bold uppercase tracking-wide text-faint">Max uses</label>
            <input
              value={maxUses}
              onChange={(event) => setMaxUses(event.target.value.replace(/\D/g, ""))}
              placeholder="∞"
              className="w-20 rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
            />
          </div>
          <label className="flex items-center gap-2 py-2 text-sm text-muted">
            <input type="checkbox" checked={unlimited} onChange={(event) => setUnlimited(event.target.checked)} />
            Unlimited builds
          </label>
          <button
            onClick={create}
            disabled={!label.trim() || busy}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
          >
            Create link
          </button>
        </div>
        {note && <p className="mt-2 break-all text-xs text-accent">{note}</p>}
      </Card>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[42rem] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-[0.65rem] uppercase tracking-wide text-faint">
              <th className="py-2">Link</th>
              <th>Label</th>
              <th>Grants</th>
              <th className="text-right">Clicks</th>
              <th className="text-right">Claimed</th>
              <th className="text-right">Sign-ins</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {codes.map((row) => (
              <tr key={row.code} className={`border-b border-line/50 ${row.active ? "" : "opacity-45"}`}>
                <td className="py-2 font-mono text-xs text-text">/i/{row.code}</td>
                <td className="text-muted">{row.label}</td>
                <td className="text-xs text-muted">
                  {[row.grantsBeta ? "beta" : null, row.unlimitedBuilds ? "unlimited" : null]
                    .filter(Boolean).join(" · ") || "tracking only"}
                  {row.maxUses ? ` · max ${row.maxUses}` : ""}
                </td>
                <td className="text-right tabular-nums">{row.clicks}</td>
                <td className="text-right tabular-nums">{row.activations}</td>
                <td className="text-right tabular-nums">{row.signIns}</td>
                <td className="py-2 text-right">
                  <button
                    onClick={() => toggle(row.code, !row.active)}
                    className="rounded-md px-2 py-1 text-xs text-faint transition hover:text-text"
                  >
                    {row.active ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
            {codes.length === 0 && (
              <tr><td colSpan={7} className="py-6 text-center text-faint">No links yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BestBuildsPanel({ token }: { token: string }) {
  const [builds, setBuilds] = useState<BestBuildRow[]>([]);
  const [form, setForm] = useState({
    championSlug: "", player: "", standing: "", items: "", boots: "", runes: "", note: "",
  });
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`/api/admin/best-builds?token=${encodeURIComponent(token)}`);
    if (!res.ok) return;
    const data = (await res.json()) as { builds: BestBuildRow[] };
    setBuilds(data.builds);
  }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const save = async () => {
    if (!form.championSlug.trim() || !form.player.trim() || busy) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch(`/api/admin/best-builds?token=${encodeURIComponent(token)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = (await res.json()) as { error?: string };
      setNote(res.ok ? `Saved ${form.championSlug}.` : data.error ?? "Could not save that.");
      if (res.ok) {
        setForm({ championSlug: "", player: "", standing: "", items: "", boots: "", runes: "", note: "" });
        await load();
      }
    } finally {
      setBusy(false);
    }
  };

  const remove = async (slug: string) => {
    await fetch(`/api/admin/best-builds?token=${encodeURIComponent(token)}&slug=${encodeURIComponent(slug)}`, {
      method: "DELETE",
    });
    await load();
  };

  const field = (key: keyof typeof form, label: string, placeholder: string, wide = false) => (
    <div className={wide ? "min-w-64 flex-[2]" : "min-w-40 flex-1"}>
      <label className="mb-1 block text-[0.65rem] font-bold uppercase tracking-wide text-faint">{label}</label>
      <input
        value={form[key]}
        onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
        placeholder={placeholder}
        className="w-full rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
      />
    </div>
  );

  return (
    <section>
      <h2 className="text-xl font-semibold tracking-tight">Best-player builds</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        What the top player on a champion actually runs, typed in by hand. Shows on the leaderboard under
        that champion. Items and runes are comma-separated; items use slugs, runes use their display names.
      </p>

      <Card className="mt-4 p-4">
        <div className="flex flex-wrap gap-2">
          {field("championSlug", "Champion slug", "graves")}
          {field("player", "Player", "in-game name")}
          {field("standing", "Standing", "Rank 1 EU")}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {field("items", "Items", "youmuus-ghostblade, infinity-edge, ...", true)}
          {field("boots", "Boots", "boots-of-dynamism")}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {field("runes", "Runes", "Conqueror, Brutal, ...", true)}
          {field("note", "Note", "how they play it", true)}
        </div>
        <button
          onClick={save}
          disabled={!form.championSlug.trim() || !form.player.trim() || busy}
          className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
        >
          Save build
        </button>
        {note && <p className="mt-2 text-xs text-accent">{note}</p>}
      </Card>

      <div className="mt-4 divide-y divide-line/60">
        {builds.map((build) => (
          <div key={build.championSlug} className="flex items-center gap-3 py-2.5">
            <span className="w-32 shrink-0 truncate text-sm font-medium">{build.championSlug}</span>
            <span className="w-40 shrink-0 truncate text-sm text-muted">{build.player}</span>
            <span className="min-w-0 flex-1 truncate text-xs text-faint">
              {[...build.items, build.boots].filter(Boolean).join(", ")}
            </span>
            <button
              onClick={() => remove(build.championSlug)}
              className="shrink-0 rounded-md px-2 py-1 text-xs text-faint transition hover:bg-bad/15 hover:text-bad"
            >
              Delete
            </button>
          </div>
        ))}
        {builds.length === 0 && <p className="py-6 text-center text-sm text-faint">Nothing recorded yet.</p>}
      </div>
    </section>
  );
}
