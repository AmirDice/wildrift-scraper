import { redirect } from "next/navigation";
import { impactPatches } from "@/lib/patch-impact";

/** /patch-impact opens the newest patch's page. */
export default function PatchImpactIndex() {
  const latest = impactPatches()[0];
  redirect(latest ? `/patch-impact/${latest}` : "/meta#builds");
}
