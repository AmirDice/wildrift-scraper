import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const site = JSON.parse(fs.readFileSync(path.join(ROOT, "web-next/src/data/site.json"), "utf8"));
const roster = JSON.parse(fs.readFileSync(path.join(ROOT, "web-next/src/data/roster.json"), "utf8"));
const details = JSON.parse(fs.readFileSync(path.join(ROOT, "web-next/src/data/champion_details.json"), "utf8"));
const fallbackCounters = JSON.parse(fs.readFileSync(path.join(ROOT, "web-next/src/data/counters.json"), "utf8"));
const validSlugs = new Set(site.champions.map((champion) => champion.slug));
const envText = fs.readFileSync(path.join(ROOT, "web-next/.env.local"), "utf8");
const apiKey = envText.match(/^DEEPSEEK_API_KEY=(.+)$/m)?.[1]?.trim();
if (!apiKey) throw new Error("DEEPSEEK_API_KEY is missing from web-next/.env.local");

const compactChampion = (champion) => {
  return {
    name: champion.name,
    slug: champion.slug,
    role: champion.role,
    class: champion.class,
  };
};

function parseJson(text) {
  const cleaned = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  return JSON.parse(cleaned);
}

async function generateBatch(role, champions, targets) {
  const rosterBlock = JSON.stringify(champions.map(compactChampion));
  const system = `You are a meticulous Wild Rift matchup analyst working on patch 7.2a. Determine direct champion matchups from kit interaction, not popularity, generic tier strength, or League PC assumptions. Games are usually 15-20 minutes and fights are short. Use Wild Rift abilities and pacing. Return valid JSON only.`;
  const user = `Analyze only these TARGET ${role} champions: ${targets.map((champion) => champion.slug).join(", ")}.
Choose their matchups from the complete SAME-ROLE candidate roster supplied below.

For each TARGET champion use your Wild Rift knowledge to choose the top 5 champions they are STRONG AGAINST and top 5 they are WEAK AGAINST. Judge the normal role interaction:
- Baron/Mid: lane control, trading pattern, wave access, all-in windows, range, sustain and escape.
- Jungle: clear tempo, invades, river skirmishes, gank reliability, objective contests and dueling.
- Dragon: lane trading with a normal support, range, all-in safety, scaling timing and teamfight access.
- Support: 2v2 lane pattern, engage/disengage, protection, roam pressure and teamfight interaction.

Rules:
1. Matchups must be based on concrete kit interaction. Do not simply select low-win-rate champions.
2. Select only the five clearest matchups for that TARGET. Do not inflate lists to make another champion's choices reciprocal.
3. Each reason must be 8-22 words and name the decisive kit interaction. Avoid unsupported numeric claims.
4. Confidence is an integer from 60 to 95. Use lower confidence for skill matchups.
5. Use only supplied slugs and never select the champion itself.
6. Never invent an interaction. In particular, do not claim projectile blockers stop beams, ground zones, passives or non-projectile ultimates; do not call damage blocking invulnerability.
7. Strong and weak lists must contain five unique slugs and cannot overlap.

Schema:
{"champion-slug":{"strong":[{"slug":"opponent-slug","reason":"...","confidence":80}],"weak":[{"slug":"opponent-slug","reason":"...","confidence":80}]}}

Champion data:
${rosterBlock}`;

  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetch("https://api.deepseek.com/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify({
          model: "deepseek-v4-flash",
          messages: [{ role: "system", content: system }, { role: "user", content: user }],
          temperature: 0,
          max_tokens: 12000,
          thinking: { type: "disabled" },
          response_format: { type: "json_object" },
        }),
        signal: AbortSignal.timeout(240_000),
      });
      if (!response.ok) throw new Error(`DeepSeek ${response.status}: ${await response.text()}`);
      const payload = await response.json();
      const content = payload.choices?.[0]?.message?.content;
      if (!content) throw new Error("model returned no content");
      const parsed = parseJson(content);
      for (const target of targets) {
        if (!parsed[target.slug]) throw new Error(`missing target ${target.slug}`);
        for (const side of ["strong", "weak"]) {
          const supplied = parsed[target.slug][side];
          if (!Array.isArray(supplied)) throw new Error(`${target.slug} ${side} must be an array`);
          const list = supplied.filter((entry, index, all) => validSlugs.has(entry?.slug) && entry.slug !== target.slug && all.findIndex((item) => item?.slug === entry.slug) === index);
          const blocked = new Set([target.slug, ...list.map((entry) => entry.slug)]);
          for (const fallback of fallbackCounters[target.slug]?.[side] ?? []) {
            const entry = typeof fallback === "string" ? { slug: fallback, reason: "A reliable kit matchup based on established Wild Rift interaction patterns.", confidence: 65 } : fallback;
            if (list.length >= 5) break;
            if (validSlugs.has(entry.slug) && !blocked.has(entry.slug)) { list.push(entry); blocked.add(entry.slug); }
          }
          parsed[target.slug][side] = list.slice(0, 5);
          if (list.length < 5) throw new Error(`${target.slug} ${side} could not be filled to five entries`);
          const slugs = list.map((entry) => entry?.slug);
          if (new Set(slugs).size !== 5 || slugs.includes(target.slug)) throw new Error(`${target.slug} ${side} contains duplicate/self matchup`);
          if (list.some((entry) => String(entry?.reason ?? "").trim().split(/\s+/).length < 7)) throw new Error(`${target.slug} ${side} contains an incomplete reason`);
        }
        const strong = new Set(parsed[target.slug].strong.map((entry) => entry.slug));
        if (parsed[target.slug].weak.some((entry) => strong.has(entry.slug))) throw new Error(`${target.slug} has an opponent on both sides`);
      }
      return parsed;
    } catch (error) {
      lastError = error;
      console.warn(`${role} batch ${targets[0]?.slug}-${targets.at(-1)?.slug} attempt ${attempt} failed; retrying`);
    }
  }
  throw new Error(`${role} batch failed after retries: ${lastError instanceof Error ? lastError.message : lastError}`);
}

const byRole = Object.groupBy(site.champions, (champion) => champion.role);
const raw = {};
const jobs = [];
for (const role of ["Baron", "Jungle", "Mid", "Dragon", "Support"]) {
  const champions = byRole[role] ?? [];
  for (let index = 0; index < champions.length; index += 7) {
    jobs.push(generateBatch(role, champions, champions.slice(index, index + 7)));
  }
}
console.log(`Generating top-five matchups in ${jobs.length} compact batches...`);
for (const result of await Promise.all(jobs)) Object.assign(raw, result);

const output = Object.fromEntries(site.champions.map((champion) => {
  const normalize = (entry) => ({
    slug: entry.slug,
    reason: String(entry.reason).trim(),
    confidence: Math.max(50, Math.min(99, Math.round(Number(entry.confidence) || 65))),
  });
  return [champion.slug, {
    strong: raw[champion.slug].strong.map(normalize).sort((a, b) => b.confidence - a.confidence),
    weak: raw[champion.slug].weak.map(normalize).sort((a, b) => b.confidence - a.confidence),
  }];
}));

let reciprocal = 0;
let contradictions = 0;
for (const [slug, entry] of Object.entries(output)) {
  for (const strong of entry.strong) {
    if (output[strong.slug]?.weak.some((item) => item.slug === slug)) reciprocal += 1;
    if (output[strong.slug]?.strong.some((item) => item.slug === slug)) contradictions += 1;
  }
}

const json = `${JSON.stringify(output, null, 2)}\n`;
fs.writeFileSync(path.join(ROOT, "data/counters.json"), json);
fs.writeFileSync(path.join(ROOT, "web-next/src/data/counters.json"), json);
console.log(`Saved top-five matchup data for ${Object.keys(output).length} champions (${reciprocal} reciprocal confirmations, ${contradictions} direct contradictions).`);
