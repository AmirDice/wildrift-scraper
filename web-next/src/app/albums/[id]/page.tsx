import type { Metadata } from "next";
import { Container } from "@/components/ui";
import { AlbumDetail } from "@/components/album-detail";

// Albums are unlisted: anyone with the link can read one, but they are not
// indexed and nothing links to them from the site.
export const metadata: Metadata = {
  title: "Build Album | WrTrueMeta",
  description: "A shared collection of Wild Rift builds.",
  robots: { index: false, follow: false },
};

export default async function AlbumPage(props: PageProps<"/albums/[id]">) {
  const { id } = await props.params;
  return (
    <Container className="py-10 sm:py-14">
      <AlbumDetail id={id} />
    </Container>
  );
}
