import { PLAYSTYLE_METRICS, playstyleLevel, type PlaystyleProfileData } from "@/lib/playstyle-profile";

export function PlaystyleProfile({ name, profile }: { name: string; profile: PlaystyleProfileData }) {
  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{name} playstyle profile</h2>
          <p className="mt-1 text-sm text-muted">A practical view of how the kit wants to play, not a power ranking.</p>
        </div>
        <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[0.65rem] font-semibold uppercase tracking-wide text-faint">
          {profile.source === "kit-profile" ? `${profile.confidence} confidence` : "role-based estimate"}
        </span>
      </div>
      <div className="mt-5 grid gap-x-6 gap-y-4 sm:grid-cols-2">
        {PLAYSTYLE_METRICS.map((metric) => {
          const value = profile.values[metric.key];
          return (
            <div key={metric.key} title={metric.hint} className="group">
              <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
                <span className="font-medium text-muted decoration-dotted underline-offset-4 group-hover:underline">{metric.label}</span>
                <span className="font-semibold text-text">{playstyleLevel(value)}</span>
              </div>
              <div className="grid grid-cols-5 gap-1" aria-label={`${metric.label}: ${playstyleLevel(value)}`}>
                {[1, 2, 3, 4, 5].map((segment) => (
                  <span
                    key={segment}
                    className={`h-2 rounded-full ${segment <= Math.ceil(value * 5) ? "bg-gradient-to-r from-accent/70 to-accent" : "bg-white/[0.07]"}`}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function PlaystyleComparison({
  leftName,
  left,
  rightName,
  right,
}: {
  leftName: string;
  left: PlaystyleProfileData;
  rightName: string;
  right: PlaystyleProfileData;
}) {
  return (
    <div className="glass rounded-2xl p-4 sm:p-5">
      <div className="mb-5 text-center">
        <h2 className="font-semibold">Playstyle comparison</h2>
        <p className="mt-1 text-xs text-muted">Kit tendencies explain how the champions differ; they do not decide who wins.</p>
      </div>
      <div className="space-y-4">
        {PLAYSTYLE_METRICS.map((metric) => {
          const lv = left.values[metric.key];
          const rv = right.values[metric.key];
          return (
            <div key={metric.key} title={metric.hint}>
              <div className="mb-1.5 grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-[0.7rem]">
                <span className="truncate text-right font-semibold text-[#4f8dff]">{playstyleLevel(lv)}</span>
                <span className="w-24 text-center text-faint sm:w-32">{metric.label}</span>
                <span className="truncate font-semibold text-[#ffd76e]">{playstyleLevel(rv)}</span>
              </div>
              <div className="grid grid-cols-2 gap-1">
                <div className="flex h-2 justify-end overflow-hidden rounded-full bg-white/[0.06]">
                  <span className="h-full rounded-full bg-[#4f8dff]" style={{ width: `${lv * 100}%` }} />
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                  <span className="block h-full rounded-full bg-[#ffd76e]" style={{ width: `${rv * 100}%` }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-4 flex justify-between text-[0.65rem] text-faint">
        <span>{leftName}</span>
        <span>{rightName}</span>
      </div>
    </div>
  );
}
