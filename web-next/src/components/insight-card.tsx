import Link from "next/link";
import { Card } from "@/components/ui";

/** A small ranked list: icon, name, optional sub-label and a right-aligned
 *  metric. Used by the home page and the meta report's deep-dive sections. */
export type InsightItem = { icon?: string; name: string; sub?: string; metric?: string; metricClass?: string; href?: string };

export function InsightCard({
  title,
  subtitle,
  items,
  href,
}: {
  title: string;
  subtitle?: string;
  items: InsightItem[];
  href?: string;
}) {
  return (
    <Card className="flex flex-col p-5">
      <h3 className="font-semibold">{title}</h3>
      {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      <div className="mt-3 flex flex-1 flex-col">
        {items.map((it, i) => {
          const row = (
            <div className="flex items-center gap-3 py-2">
              {it.icon ? (
                // eslint-disable-next-line @next/next/no-img-element
                <span className="h-7 w-7 shrink-0 overflow-hidden rounded-full ring-1 ring-white/10">
                  <img src={it.icon} alt="" width={28} height={28} loading="lazy" className="h-full w-full scale-[1.12] object-cover" />
                </span>
              ) : (
                <span className="h-7 w-7 shrink-0 rounded-full bg-white/[0.06]" />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{it.name}</p>
                {it.sub && <p className="truncate text-xs text-muted">{it.sub}</p>}
              </div>
              {it.metric && <span className={`text-sm font-semibold ${it.metricClass ?? "text-text"}`}>{it.metric}</span>}
            </div>
          );
          return (
            <div key={i} className={i > 0 ? "border-t border-line/60" : ""}>
              {it.href ? <Link href={it.href} className="block transition hover:opacity-80">{row}</Link> : row}
            </div>
          );
        })}
      </div>
      {href && (
        <Link
          href={href}
          className="mt-3 border-t border-line/60 pt-3 text-sm font-medium text-accent transition hover:opacity-80"
        >
          View more →
        </Link>
      )}
    </Card>
  );
}
