import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Container } from "@/components/ui";
import { BlogBody } from "@/components/blog-body";
import { getPost, getPosts, readingMinutes } from "@/lib/blog";
import { JsonLd, breadcrumbJsonLd } from "@/lib/structured-data";

export function generateStaticParams() {
  return getPosts().map((post) => ({ slug: post.slug }));
}

export async function generateMetadata(props: PageProps<"/blog/[slug]">): Promise<Metadata> {
  const { slug } = await props.params;
  const post = getPost(slug);
  if (!post) return { title: "Guide not found" };
  return {
    title: post.title,
    description: post.description,
    alternates: { canonical: `/blog/${post.slug}` },
    openGraph: {
      type: "article",
      title: post.title,
      description: post.description,
      publishedTime: post.date,
    },
    twitter: { card: "summary_large_image", title: post.title, description: post.description },
  };
}

const DATE_FORMAT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "long",
  day: "numeric",
  timeZone: "UTC",
});

export default async function BlogPostPage(props: PageProps<"/blog/[slug]">) {
  const { slug } = await props.params;
  const post = getPost(slug);
  if (!post) notFound();

  const others = getPosts().filter((entry) => entry.slug !== post.slug).slice(0, 3);

  // Article structured data: these pages exist to be found in search, and the
  // ranked lists inside them are exactly what a rich result wants to surface.
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: post.title,
    description: post.description,
    datePublished: post.date,
    dateModified: post.date,
    author: { "@type": "Organization", name: "WrTrueMeta" },
    publisher: { "@type": "Organization", name: "WrTrueMeta" },
    mainEntityOfPage: `https://wrtruemeta.com/blog/${post.slug}`,
  };

  return (
    <Container className="py-10 sm:py-14">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Guides", path: "/blog" },
          { name: post.title, path: `/blog/${post.slug}` },
        ])}
      />

      <article className="mx-auto max-w-2xl">
        <Link href="/blog" className="text-sm font-medium text-accent transition hover:opacity-80">
          ← All guides
        </Link>
        <div className="mt-4 flex items-center gap-2">
          <span className="rounded bg-accent/15 px-2 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-accent">
            {post.tag}
          </span>
          <span className="text-xs text-faint">
            {DATE_FORMAT.format(new Date(post.date))} · {readingMinutes(post)} min read
          </span>
        </div>
        <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">{post.title}</h1>
        <p className="mt-4 text-lg leading-relaxed text-text/90">{post.lede}</p>

        <BlogBody blocks={post.blocks} />
      </article>

      {others.length > 0 && (
        <div className="mx-auto mt-14 max-w-2xl border-t border-line pt-8">
          <h2 className="text-sm font-bold uppercase tracking-wide text-faint">Keep reading</h2>
          <div className="mt-4 space-y-3">
            {others.map((entry) => (
              <Link key={entry.slug} href={`/blog/${entry.slug}`} className="block transition hover:opacity-80">
                <p className="font-medium">{entry.title}</p>
                <p className="text-sm text-muted">{entry.description}</p>
              </Link>
            ))}
          </div>
        </div>
      )}
    </Container>
  );
}
