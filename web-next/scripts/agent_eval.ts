/** Run questions through the site agent's real routing and print what a
 *  visitor would get.
 *
 *  The analytics say 93% of agent answers come from the keyword fast path in
 *  lib/agent-context.ts, not the model, so the fast path IS the agent for most
 *  visitors. This replays a battery against it: which path answered, and what
 *  it said. Questions the fast path declines are written out with the exact
 *  context the model would receive, for scripts/agent_eval.py to send.
 *
 *    npx tsx scripts/agent_eval.ts <battery.json> <out.json>
 */
import * as fs from "fs";
import { buildAgentContext, championSlugFromQuestion, resolveAgentAnswer } from "../src/lib/agent-context";

type Case = { q: string; page?: string };

const [, , batteryPath, outPath] = process.argv;
const battery: Case[] = JSON.parse(fs.readFileSync(batteryPath, "utf-8"));
const out = battery.map(({ q, page = "/" }) => {
  const pageSlug = page.match(/^\/champions\/([^/?#]+)/)?.[1] ?? "";
  const context = buildAgentContext(page, championSlugFromQuestion(q) || pageSlug, q);
  const answer = resolveAgentAnswer(q, context);
  return {
    q,
    page,
    champion: context.champion?.name ?? null,
    path: answer ? "data" : "model",
    answer: answer?.answer ?? null,
    contextBytes: JSON.stringify(context).length,
    context: answer ? undefined : context,
  };
});
fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
for (const row of out) {
  console.log(`[${row.path}] (${row.page}${row.champion ? ` | ${row.champion}` : ""}) ${row.q}`);
  if (row.answer) console.log("   " + row.answer.replace(/\n+/g, " / ").slice(0, 260));
}
