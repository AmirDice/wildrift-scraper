"use client";

import { useRouter } from "next/navigation";
import { ChampionCombobox, type ComboItem } from "@/components/champion-combobox";

export function HomeSearch({ champions }: { champions: ComboItem[] }) {
  const router = useRouter();
  return (
    <div className="mx-auto mt-8 max-w-md">
      <ChampionCombobox
        champions={champions}
        placeholder="Search any champion…"
        onSelect={(slug) => router.push(`/champions/${slug}`)}
      />
    </div>
  );
}
