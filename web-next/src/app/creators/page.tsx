import type { Metadata } from "next";
import { Container, Card } from "@/components/ui";
import { CreatorDirectory } from "@/components/creator-directory";
import { DiscordButton } from "@/components/discord";
import { CREATOR_CATEGORIES, activeCategories } from "@/lib/creators";
import { creatorDirectoryUpdatedAt, listCreators } from "@/lib/creator-store";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Wild Rift Creators to Follow | YouTubers, Streamers & Guides",
  description:
    "A directory of Wild Rift content creators who are still uploading: educational channels, high-elo gameplay, guides, esports coverage and funny content, with links to every platform they post on.",
  alternates: { canonical: "/creators" },
};

export default async function CreatorsPage() {
  const creators = await listCreators();
  const categories = activeCategories(creators);
  const updatedAt = await creatorDirectoryUpdatedAt();

  return (
    <Container className="py-10 sm:py-14">
      <div className="max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Community</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          Wild Rift creators worth following
        </h1>
        <p className="mt-3 leading-relaxed text-muted">
          The Wild Rift creator scene is scattered across YouTube, TikTok and Twitch, and half the lists you
          find are full of channels that stopped uploading two years ago. This one only lists creators who are
          still posting, sorted by what they actually make.
        </p>
      </div>

      {creators.length > 0 ? (
        <>
          <div className="mt-8">
            <CreatorDirectory
              creators={creators}
              categories={categories.map((category) => ({ ...category }))}
            />
          </div>
          <p className="mt-8 text-xs text-faint">
            Last checked {updatedAt}. Know someone missing, or a channel that has gone quiet? Tell us
            in the Discord and the list gets fixed.
          </p>
        </>
      ) : (
        <EmptyState />
      )}
    </Container>
  );
}

/**
 * Shown while the directory has no entries.
 *
 * It deliberately does not fill the page with placeholder creators: every name
 * here is a real person, and a made-up directory is worse than an empty one.
 */
function EmptyState() {
  return (
    <div className="mt-8 space-y-6">
      <Card className="p-6">
        <h2 className="text-lg font-semibold">The list is being built</h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          Rather than pad this page with channels we have not opened, it stays empty until each entry is
          verified: the real channel link, the platforms they actually post on, and a date someone last
          checked they were still uploading.
        </p>
        <div className="mt-4">
          <DiscordButton>Suggest a creator in Discord</DiscordButton>
        </div>
      </Card>

      <div>
        <h2 className="text-sm font-bold uppercase tracking-wide text-faint">Categories the list covers</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {CREATOR_CATEGORIES.map((category) => (
            <Card key={category.key} className="p-4">
              <p className="font-semibold">{category.label}</p>
              <p className="mt-1 text-sm text-muted">{category.blurb}</p>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
