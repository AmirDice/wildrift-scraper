"use client";

import type { Advice } from "@/components/enemy-build";

/* eslint-disable @typescript-eslint/no-explicit-any */

/**
 * Local-only inspection surface for Build Studio.  The advisor deliberately
 * returns structured tournament evidence; this panel makes that evidence
 * visible without adding any of it to the normal production UI.
 */
export function AdvisorDebugPanel({ advice }: { advice: Advice }) {
  if (process.env.NODE_ENV === "production") return null;

  const tournament = advice.engineTournament;
  const search = tournament?.engineSearch;
  const modelCandidates = tournament?.modelCandidates ?? [];
  const topEngine = search?.topEngineBuilds ?? [];
  const measurements = tournament?.measurements ?? [];
  const paths = Object.entries(search?.paths ?? {});
  const engineTie = search?.engineTie as {
    isTie?: boolean;
    scoreGap?: number;
    scoreMargin?: number;
    candidates?: Array<Record<string, unknown>>;
  } | undefined;
  const runePolicy = search?.runePolicy as {
    requested?: string;
    mode?: string;
    testedPages?: number;
    frontlineDefensivePageRequired?: boolean;
    selectedDefensivePage?: boolean;
  } | undefined;
  const bootPolicy = search?.bootPolicy as {
    requested?: string;
    defensiveBootCloseRace?: boolean;
  } | undefined;

  return (
    <details className="rounded-2xl border border-cyan-400/25 bg-cyan-400/[0.04] p-4 text-xs">
      <summary className="cursor-pointer select-none font-bold uppercase tracking-wide text-cyan-300">
        Local advisor debug · model + engine trace
      </summary>
      <div className="mt-4 space-y-4 text-muted">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Provenance" value={advice.provenance ?? "—"} />
          <Metric label="Tournament winner" value={String(tournament?.winner ?? tournament?.judgedWinner ?? "—")} />
          <Metric label="Model candidates" value={`${modelCandidates.length}/${tournament?.modelCandidateCount ?? "—"}`} />
          <Metric label="Engine candidates" value={String(tournament?.candidateCount ?? "—")} />
        </div>

        {tournament?.engineWinGate ? (
          <div className={`rounded-lg border p-3 ${tournament.engineAutoSelected
            ? "border-emerald-400/40 bg-emerald-400/[0.08] text-emerald-100"
            : "border-cyan-400/25 bg-cyan-400/[0.04] text-cyan-100"}`}>
            <p className="font-bold uppercase tracking-wide">
              Engine win gate: {tournament.engineAutoSelected ? "automatic engine selection" : "advisory only"}
            </p>
            <p className="mt-1 text-[0.7rem] leading-relaxed">
              Lead {((tournament.engineWinGate.relativeLead ?? 0) * 100).toFixed(1)}% ·
              required {((tournament.engineWinGate.marginThreshold ?? 0.05) * 100).toFixed(0)}% ·
              margin {tournament.engineWinGate.marginSatisfied ? "met" : "not met"} ·
              coverage {tournament.engineWinGate.coverageSafe ? "safe" : "has gaps"} ·
              trust {tournament.engineWinGate.trustLevel ?? "unknown"}.
              {tournament.engineWinGate.reason ? ` ${tournament.engineWinGate.reason}.` : ""}
            </p>
            {tournament.engineWinGate.comparisonCandidates?.length ? (
              <p className="mt-1 text-[0.68rem] text-cyan-200/80">
                Coverage checked: {tournament.engineWinGate.comparisonCandidates.join(" vs ")}
              </p>
            ) : null}
            {tournament.engineWinGate.majorCoverageGaps?.length ? (
              <p className="mt-1 text-[0.68rem] text-amber-200">
                Major gaps: {tournament.engineWinGate.majorCoverageGaps.join("; ")}
              </p>
            ) : null}
          </div>
        ) : null}

        {engineTie ? (
          <div className="rounded-lg border border-violet-400/25 bg-violet-400/[0.05] p-3 text-violet-100">
            <p className="font-bold uppercase tracking-wide">
              Engine tie: {engineTie.isTie ? "close alternatives" : "clear leader"}
            </p>
            <p className="mt-1 text-[0.7rem] leading-relaxed">
              Gap {Number(engineTie.scoreGap ?? 0).toFixed(3)} · tie band {Number(engineTie.scoreMargin ?? 0).toFixed(3)}.
              {engineTie.isTie ? " Gemini receives the alternatives and returns one practical build." : " The normal response stays on one build."}
            </p>
          </div>
        ) : null}

        {(runePolicy || bootPolicy) ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {runePolicy ? (
              <Metric label="Rune policy" value={`${runePolicy.mode === "model-and-ladder-pages-only" ? "model + ladder pages" : "score-ranked page"} · ${runePolicy.testedPages ?? "—"} tested${runePolicy.selectedDefensivePage ? " · defensive winner" : ""}${runePolicy.frontlineDefensivePageRequired ? " · frontline guard" : ""}`} />
            ) : null}
            {bootPolicy ? (
              <Metric label="Boot policy" value={bootPolicy.defensiveBootCloseRace ? "defensive close-race winner" : "score-ranked boots"} />
            ) : null}
          </div>
        ) : null}

        {tournament?.ran === false ? (
          <div className="rounded-lg border border-amber-400/40 bg-amber-400/[0.08] p-3 text-amber-200">
            <p className="font-bold uppercase tracking-wide">Engine tournament skipped</p>
            {tournament.stage ? <p className="mt-1 text-[0.68rem] text-amber-300/80">Stage: {tournament.stage}</p> : null}
            <p className="mt-1 break-words text-[0.72rem] leading-relaxed">
              {tournament.reason ?? "The advisor fell back before tournament metadata was produced."}
            </p>
            {tournament.fellBackTo ? <p className="mt-1 text-[0.68rem] text-amber-300/80">Fallback: {tournament.fellBackTo}</p> : null}
          </div>
        ) : null}

        {tournament?.coreRepairedAfterJudge ? (
          <p className="rounded-lg border border-amber-400/30 bg-amber-400/[0.05] p-2 text-[0.7rem] text-amber-200">
            The judge selected {tournament.judgedWinner ?? "a tested candidate"}, but a deterministic post-judge repair changed its core; the engine label was withheld until this is re-measured.
          </p>
        ) : null}

        {tournament?.winnerRationale?.length ? (
          <p className="rounded-lg border border-cyan-400/25 bg-cyan-400/[0.04] p-2 text-[0.7rem] text-cyan-100">
            {tournament.winnerRationale.join(" ")}
          </p>
        ) : null}

        {tournament?.candidateErrors?.length ? (
          <section>
            <Heading>Candidate validation warnings</Heading>
            <ul className="list-disc space-y-1 pl-5 text-amber-300">
              {tournament.candidateErrors.map((error, i) => <li key={`${error}-${i}`}>{error}</li>)}
            </ul>
          </section>
        ) : null}

        <section>
          <Heading>Model candidate builds</Heading>
          {modelCandidates.length ? (
            <div className="grid gap-2 md:grid-cols-3">
              {modelCandidates.map((candidate, i) => (
                <pre key={String(candidate.id ?? i)} className="overflow-auto rounded-lg bg-black/25 p-2 text-[0.68rem] leading-relaxed text-text">
                  {JSON.stringify(candidate, null, 2)}
                </pre>
              ))}
            </div>
          ) : <Empty />}
        </section>

        <section>
          <Heading>Ladder comparison build</Heading>
          {tournament?.ladderCandidate ? (
            <pre className="overflow-auto rounded-lg bg-black/25 p-2 text-[0.68rem] leading-relaxed text-text">
              {JSON.stringify(tournament.ladderCandidate, null, 2)}
            </pre>
          ) : <Empty />}
        </section>

        <section>
          <Heading>Model item scores · returned (first 30)</Heading>
          {advice.candidateItemScores?.length ? (
            <div className="grid gap-x-5 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
              {advice.candidateItemScores.slice(0, 30).map((row, i) => (
                <div key={`${row.item}-${i}`} className="flex items-center justify-between gap-2 border-b border-line/40 py-1">
                  <span className="truncate text-text">{i + 1}. {row.item}</span>
                  <span className="shrink-0 text-cyan-300">{row.score}</span>
                </div>
              ))}
            </div>
          ) : <Empty />}
        </section>

        <section>
          <Heading>Engine search</Heading>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Objective" value={String(search?.objective ?? "—")} />
            <Metric label="Prefilter trials" value={String(search?.searched ?? "—")} />
            <Metric label="Scenario finalists" value={String(search?.scenarioEvaluations ?? "—")} />
            <Metric label="Authored → challenger" value={`${search?.authoredBestScore ?? "—"} → ${search?.challengerScore ?? "—"}`} />
          </div>
          {paths.length ? (
            <div className="mt-3 space-y-3">
              {paths.map(([path, meta]) => (
                <div key={path}>
                  <p className="mb-1 font-semibold text-text">{path} · {meta.boundedPool ?? 0} pool / {meta.legalCombinations ?? 0} legal combinations</p>
                  <div className="grid gap-x-5 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
                    {(meta.topItems ?? []).map((row, i) => (
                      <div key={`${path}-${row.item}`} className="flex justify-between gap-2 border-b border-line/30 py-1">
                        <span className="truncate">{i + 1}. {row.item}</span>
                        <span className="text-cyan-300">{row.score}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : <Empty />}
        </section>

        <section>
          <Heading>Component / recipe coverage</Heading>
          <p className="mb-2">{Math.round((advice.engineEvidence?.recipeCoverage ?? 0) * 100)}% of completed items have authoritative recipe data. Empty recipes are intentionally not invented.</p>
          {advice.engineEvidence?.componentPlan?.length ? (
            <pre className="overflow-auto rounded-lg bg-black/25 p-2 text-[0.68rem] leading-relaxed text-text">
              {JSON.stringify(advice.engineEvidence.componentPlan, null, 2)}
            </pre>
          ) : <Empty />}
        </section>

        <section>
          <Heading>Engine top builds</Heading>
          {topEngine.length ? (
            <div className="space-y-2">
              {topEngine.map((build, i) => (
                <pre key={String(build.id ?? i)} className="overflow-auto rounded-lg bg-black/25 p-2 text-[0.68rem] leading-relaxed text-text">
                  {JSON.stringify({ rank: i + 1, ...build }, null, 2)}
                </pre>
              ))}
            </div>
          ) : <Empty />}
        </section>

        <section>
          <Heading>Measured candidates</Heading>
          {measurements.length ? (
            <pre className="max-h-96 overflow-auto rounded-lg bg-black/25 p-2 text-[0.68rem] leading-relaxed text-text">
              {JSON.stringify(measurements, null, 2)}
            </pre>
          ) : <Empty />}
        </section>

        <section>
          <Heading>Complete response</Heading>
          <pre className="max-h-[32rem] overflow-auto rounded-lg bg-black/25 p-2 text-[0.68rem] leading-relaxed text-text">
            {JSON.stringify(advice, null, 2)}
          </pre>
        </section>
      </div>
    </details>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return <p className="mb-2 font-bold uppercase tracking-wide text-faint">{children}</p>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border border-line/40 bg-black/15 p-2"><span className="block text-[0.62rem] uppercase tracking-wide text-faint">{label}</span><span className="font-semibold text-text">{value}</span></div>;
}

function Empty() {
  return <p className="rounded-lg bg-black/15 p-2 text-faint">No data returned for this generation.</p>;
}
