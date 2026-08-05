import { permanentRedirect } from "next/navigation";

/**
 * The Counter Builder moved into the Build Studio as the "Build vs Enemy Team"
 * tab.
 *
 * It kept its own page for as long as it was a separate tool, and that cost it:
 * 110 visits against the tier list's 498, because a second page is a second
 * thing to find. It answers the same question the Personal Build Generator does
 * with one extra input, so it belongs beside it rather than one navigation away.
 *
 * The route survives as a redirect rather than a 404. Shared counter links,
 * Discord posts and the old nav entry all point here, and every one of them
 * still has to land on the tool. The champion travels with it.
 */
export default async function CounterPage(props: PageProps<"/counter">) {
  const search = await props.searchParams;
  const champion = typeof search.champion === "string" ? search.champion : "";
  permanentRedirect(
    champion ? `/build?champion=${encodeURIComponent(champion)}&tab=counter` : "/build?tab=counter",
  );
}
