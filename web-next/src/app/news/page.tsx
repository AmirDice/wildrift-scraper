import type { Metadata } from "next";
import newsData from "@/data/news.json";
import { Container } from "@/components/ui";

/* eslint-disable @next/next/no-img-element */

type Article = {
  title: string;
  excerpt: string;
  date: string | null;
  url: string | null;
  category: string;
  image: string | null;
};

const NEWS = newsData as unknown as { source: string; articles: Article[] };

export const metadata: Metadata = {
  title: "Wild Rift News — Latest Patches, Champions & Updates",
  description:
    "The latest League of Legends: Wild Rift news — new champions, patch notes, skins and game updates, straight from the official source.",
  alternates: { canonical: "/news" },
};

function fmtDate(d: string | null) {
  if (!d) return "";
  return new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export default function NewsPage() {
  const articles = NEWS.articles;
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Wild Rift News</h1>
      <p className="mt-2 max-w-2xl text-muted">
        The latest patches, champions and updates — pulled from the official Wild Rift site. Tap any
        story to read it in full.
      </p>

      <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {articles.map((a) => (
          <a
            key={a.title}
            href={a.url ?? NEWS.source}
            target="_blank"
            rel="noopener noreferrer"
            className="glass glass-hover group flex flex-col overflow-hidden rounded-2xl"
          >
            {a.image && (
              <div className="aspect-video overflow-hidden">
                <img
                  src={a.image}
                  alt=""
                  loading="lazy"
                  className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
                />
              </div>
            )}
            <div className="flex flex-1 flex-col p-4">
              <div className="flex items-center gap-2 text-[0.7rem] font-semibold uppercase tracking-wide">
                <span className="text-accent">{a.category}</span>
                <span className="text-faint">·</span>
                <span className="text-faint">{fmtDate(a.date)}</span>
              </div>
              <h2 className="mt-2 font-semibold leading-snug transition group-hover:text-accent">
                {a.title}
              </h2>
              {a.excerpt && <p className="mt-1.5 line-clamp-3 text-sm text-muted">{a.excerpt}</p>}
            </div>
          </a>
        ))}
      </div>

      <p className="mt-8 text-xs text-faint">
        News sourced from the official Wild Rift site. WrTrueMeta is an independent fan project, not
        affiliated with Riot Games.
      </p>
    </Container>
  );
}
