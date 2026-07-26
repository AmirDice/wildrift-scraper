import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TAG_URL = "https://wildrift.leagueoflegends.com/en-us/news/tags/patch-notes/";
const OUT = resolve(ROOT, "data", "official_patch_history.json");
const HISTORY_OUT = resolve(ROOT, "data", "champion_change_history.json");
const WEB_HISTORY_OUT = resolve(ROOT, "web-next", "src", "data", "champion_change_history.json");
const SUMMARY_OUT = resolve(ROOT, "web-next", "src", "data", "champion_change_summary.json");
const CONCURRENCY = 8;

async function writeJsonWithRetry(path, value) {
  let lastError;
  for (let attempt = 1; attempt <= 8; attempt += 1) {
    try {
      await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
      return;
    } catch (error) {
      lastError = error;
      await new Promise((resolveDelay) => setTimeout(resolveDelay, attempt * 250));
    }
  }
  throw lastError;
}

function nextData(html) {
  const marker = html.split('__NEXT_DATA__')[1];
  if (!marker) throw new Error("Riot page did not include __NEXT_DATA__");
  const body = marker.slice(marker.indexOf(">") + 1, marker.indexOf("</script>"));
  return JSON.parse(body);
}

function decodeHtml(value = "") {
  return value
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>|<\/li>|<\/h[1-6]>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;|&#34;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/\r/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function collectBodies(value, output = [], seen = new Set()) {
  if (!value || typeof value !== "object") return output;
  if (Array.isArray(value)) {
    for (const child of value) collectBodies(child, output, seen);
    return output;
  }
  for (const [key, child] of Object.entries(value)) {
    if (key === "body" && typeof child === "string") {
      const text = decodeHtml(child);
      if (text && !seen.has(text)) {
        seen.add(text);
        output.push(text);
      }
    } else if (!new Set(["media", "imageMedia", "icon", "analytics", "jsonLd", "hreflangs", "items"]).has(key)) {
      collectBodies(child, output, seen);
    }
  }
  return output;
}

function patchFromTitle(title) {
  return title.match(/patch notes\s+([0-9]+(?:\.[0-9]+)?[a-z]?)/i)?.[1] ?? title;
}

async function fetchText(url) {
  const response = await fetch(url, { headers: { "user-agent": "wildrift-stat-audit/1.0" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.text();
}

function championChanges(blades) {
  return blades.flatMap((blade) => {
    const scope = blade.title ?? "Champion changes";
    const modeOnly = /ARAM|ARENA|DUEL|MODE|SPELLBOOK|ONE FOR ALL/i.test(scope);
    return (blade.characters ?? []).map((entry) => ({
      champion: entry.character?.name ?? "Unknown",
      scope,
      modeOnly,
      summary: decodeHtml(entry.summary?.body ?? ""),
      changes: (entry.changes ?? []).map((change) => ({
        ability: change.title ?? "General",
        text: decodeHtml(change.description?.body ?? ""),
      })),
    }));
  });
}

function legacyChanges(patch, canonical) {
  const events = [];
  const championByUpper = new Map(canonical);
  const modeHeading = /ARAM|ARENA|DUEL|SPELLBOOK|ONE FOR ALL|URF|ALL RANDOM/i;
  const sectionHeading = /^(ITEM|RUNE|SYSTEM|GAMEPLAY|BATTLEFIELD|SUMMONER SPELL|SKIN|ACCESSORY|BUG FIX|NEW)\b/i;

  for (const block of patch.textBlocks ?? []) {
    const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
    let active = null;
    let modeOnly = false;
    const flush = () => {
      if (!active || active.lines.length === 0) return;
      const text = active.lines.join("\n");
      if (!text.includes("\u2192") && !/\b(new|removed|increased|reduced|cooldown|damage|health|mana|armor|resist|ratio|duration|range)\b/i.test(text)) return;
      const inferredModeOnly = active.modeOnly || /^(Damage dealt|Damage received|Healing done|Shielding done|Ultimate haste):/im.test(text);
      const firstChange = active.lines.findIndex((line) => line.includes("\u2192") || /^(Base Stats|\((?:P|1|2|3|4|Ult)\)|Passive|Cooldown|Damage|Health|Mana|Armor|Magic Resist)/i.test(line));
      events.push({
        champion: active.name,
        scope: inferredModeOnly ? "Mode-specific changes" : "Champion changes (legacy article)",
        modeOnly: inferredModeOnly,
        summary: firstChange > 0 ? active.lines.slice(0, firstChange).join(" ") : "",
        changes: [{ ability: "Patch notes", text }],
      });
    };

    for (const line of lines) {
      const upper = line.toUpperCase();
      if (/CHAMPION (CHANGES|ADJUSTMENTS)/i.test(line)) {
        flush();
        active = null;
        modeOnly = false;
        continue;
      }
      if (modeHeading.test(line) && /CHANGE|ADJUST|BALANCE|CHAMPION/i.test(line)) {
        flush();
        active = null;
        modeOnly = true;
        continue;
      }
      if (sectionHeading.test(line) && !championByUpper.has(upper)) {
        flush();
        active = null;
        continue;
      }
      const champion = championByUpper.get(upper);
      if (champion) {
        flush();
        active = { name: champion, modeOnly, lines: [] };
        continue;
      }
      if (active) active.lines.push(line);
    }
    flush();
  }
  return events;
}

async function fetchPatch(item) {
  const relative = item.action?.payload?.url;
  if (!relative) return null;
  const url = new URL(relative.endsWith("/") ? relative : `${relative}/`, TAG_URL).href;
  const html = await fetchText(url);
  const page = nextData(html).props?.pageProps?.page ?? {};
  const blades = page.blades ?? [];
  const blocks = collectBodies(blades);
  return {
    patch: patchFromTitle(item.title),
    title: item.title,
    publishedAt: item.publishedAt ?? item.analytics?.publishDate ?? null,
    url,
    championChanges: championChanges(blades),
    textBlocks: blocks,
    changeLines: [...new Set(blocks.flatMap((block) => block.split("\n"))
      .map((line) => line.trim())
      .filter((line) => line.includes("\u2192") || /^(New|Removed|Base Stats|Cooldown|Damage|Healing|Shield|Armor|Magic Resist|Attack Damage|Attack Speed|Mana|Health|Movement Speed)/i.test(line)))],
  };
}

async function buildChampionHistory(patches) {
  const roster = JSON.parse(await readFile(resolve(ROOT, "data", "champions_wr.json"), "utf8"));
  const canonical = new Map(roster.map((champion) => [champion.name.toUpperCase(), champion.name]));
  const history = {};
  const add = (rawName, entry) => {
    const name = canonical.get(rawName.toUpperCase()) ?? rawName;
    (history[name] ??= []).push(entry);
  };

  for (const patch of patches.filter((entry) => entry && !entry.error)) {
    const structuredKeys = new Set();
    for (const change of patch.championChanges ?? []) {
      structuredKeys.add(`${change.champion.toUpperCase()}|${change.modeOnly ? "mode" : "standard"}`);
      add(change.champion, {
        patch: patch.patch,
        publishedAt: patch.publishedAt,
        url: patch.url,
        kind: "balance",
        scope: change.scope,
        modeOnly: change.modeOnly,
        summary: change.summary,
        changes: change.changes,
      });
    }
    for (const change of legacyChanges(patch, canonical)) {
      const key = `${change.champion.toUpperCase()}|${change.modeOnly ? "mode" : "standard"}`;
      if (structuredKeys.has(key)) continue;
      add(change.champion, {
        patch: patch.patch,
        publishedAt: patch.publishedAt,
        url: patch.url,
        kind: "balance",
        scope: change.scope,
        modeOnly: change.modeOnly,
        summary: change.summary,
        changes: change.changes,
      });
    }
    const bugLines = (patch.textBlocks ?? []).flatMap((block) => block.split("\n"))
      .map((line) => line.trim())
      .filter((line) => /fixed|bug|incorrect|issue/i.test(line));
    for (const [upperName, name] of canonical) {
      for (const line of bugLines.filter((candidate) => candidate.toUpperCase().includes(upperName))) {
        add(name, {
          patch: patch.patch,
          publishedAt: patch.publishedAt,
          url: patch.url,
          kind: "bugfix",
          scope: "Bug fixes",
          modeOnly: /ARAM|ARENA|DUEL|SPELLBOOK|ONE FOR ALL/i.test(line),
          summary: line,
          changes: [],
        });
      }
    }
  }

  for (const entries of Object.values(history)) {
    entries.sort((left, right) => String(left.publishedAt).localeCompare(String(right.publishedAt)));
  }
  return history;
}

async function main() {
  let patches;
  if (process.argv.includes("--from-cache")) {
    patches = JSON.parse(await readFile(OUT, "utf8")).patches;
    process.stdout.write(`Loaded ${patches.length} cached patch notes\n`);
  } else {
    const tagPage = nextData(await fetchText(TAG_URL)).props?.pageProps?.page;
    const items = (tagPage?.blades ?? []).flatMap((blade) => blade.items ?? [])
      .filter((item) => /^Wild Rift Patch Notes\s+/i.test(item.title ?? ""));
    patches = new Array(items.length);
    let cursor = 0;
    async function worker() {
      while (cursor < items.length) {
        const index = cursor++;
        try {
          patches[index] = await fetchPatch(items[index]);
          process.stdout.write(`\rFetched ${patches.filter(Boolean).length}/${items.length}`);
        } catch (error) {
          patches[index] = { title: items[index].title, error: String(error) };
        }
      }
    }
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  }
  const archive = {
    schemaVersion: 1,
    source: TAG_URL,
    fetchedAt: new Date().toISOString(),
    purpose: "Official chronological evidence archive. Only standard-Rift changes should be promoted into live canonical data.",
    patches,
  };
  await mkdir(dirname(OUT), { recursive: true });
  await writeJsonWithRetry(OUT, archive);
  const championHistory = await buildChampionHistory(patches);
  const summary = Object.fromEntries(Object.entries(championHistory).map(([champion, entries]) => {
    const standard = entries.filter((entry) => !entry.modeOnly);
    const balance = standard.filter((entry) => entry.kind === "balance");
    const latest = standard.at(-1);
    const latestBalance = balance.at(-1);
    return [champion, {
      totalChanges: entries.length,
      modeOnlyChanges: entries.filter((entry) => entry.modeOnly).length,
      balanceChanges: balance.length,
      lastChangedPatch: latest?.patch ?? null,
      lastChangedAt: latest?.publishedAt ?? null,
      lastBalancePatch: latestBalance?.patch ?? null,
      lastBalanceAt: latestBalance?.publishedAt ?? null,
    }];
  }));
  const historyPayload = { schemaVersion: 1, champions: championHistory };
  await writeJsonWithRetry(HISTORY_OUT, historyPayload);
  await writeJsonWithRetry(WEB_HISTORY_OUT, historyPayload);
  await mkdir(dirname(SUMMARY_OUT), { recursive: true });
  await writeJsonWithRetry(SUMMARY_OUT, { schemaVersion: 1, champions: summary });
  process.stdout.write(`\nWrote ${OUT} (${patches.filter((patch) => patch && !patch.error).length} successful)\n`);
  process.stdout.write(`Wrote ${HISTORY_OUT} (${Object.keys(championHistory).length} champion timelines)\n`);
}

await main();
