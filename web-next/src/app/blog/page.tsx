import type { Metadata } from "next";
import Link from "next/link";
import { Container, Card } from "@/components/ui";
import { getPosts, readingMinutes } from "@/lib/blog";

export const metadata: Metadata = {
  title: "Wild Rift Guides & Meta Analysis | WrTrueMeta Blog",
  description:
    "Wild Rift guides grounded in real data: the best champions per role each patch, who to climb with, what China is playing before the West, and how balance changes land.",
  alternates: { canonical: "/blog" },
};

const DATE_FORMAT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "long",
  day: "numeric",
  timeZone: "UTC",
});

export default function BlogIndexPage() {
  const posts = getPosts();

  return (
    <Container className="py-10 sm:py-14">
      <div className="max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Guides</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          Wild Rift, explained with the actual numbers
        </h1>
        <p className="mt-3 leading-relaxed text-muted">
          Every ranking in these guides is resolved from the same dataset the rest of the site runs on, so
          they update with each scrape instead of ageing into a patch that no longer exists.
        </p>
      </div>

      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {posts.map((post) => (
          <Link key={post.slug} href={`/blog/${post.slug}`}>
            <Card className="glass-hover flex h-full flex-col p-5">
              <div className="flex items-center gap-2">
                <span className="rounded bg-accent/15 px-2 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-accent">
                  {post.tag}
                </span>
                <span className="text-xs text-faint">
                  {DATE_FORMAT.format(new Date(post.date))} · {readingMinutes(post)} min read
                </span>
              </div>
              <h2 className="mt-2.5 text-lg font-semibold leading-snug">{post.title}</h2>
              <p className="mt-1.5 flex-1 text-sm leading-relaxed text-muted">{post.description}</p>
              <span className="mt-3 text-sm font-semibold text-accent">Read the guide →</span>
            </Card>
          </Link>
        ))}
      </div>
    </Container>
  );
}
