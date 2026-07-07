import { redirect } from "next/navigation";

// The build optimizer is behind a "coming soon" gate for now, so individual
// build pages send visitors back to the index. The real page (git history)
// returns once the feature ships with the next patch.
export default function BuildPage() {
  redirect("/build");
}
