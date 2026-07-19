import { redirect } from "next/navigation";

// The build optimizer graduated from /build-preview to /build. Keep the old
// path working by redirecting; nothing should link here anymore.
export default function BuildPreviewPage() {
  redirect("/build");
}
