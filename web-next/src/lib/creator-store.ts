import {
  CREATOR_CATEGORIES,
  CREATORS_UPDATED_AT,
  PLATFORMS,
  getCreators as getSeedCreators,
  type Creator,
} from "@/lib/creators";
import { kvGetJson, kvSetJson } from "@/lib/kv";

export interface ManagedCreator extends Creator {
  id: string;
  updatedAt: string;
}

const DIRECTORY_KEY = "creator:directory";
const creatorId = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80);

export async function listManagedCreators(): Promise<ManagedCreator[]> {
  const creators = await kvGetJson<ManagedCreator[]>(DIRECTORY_KEY, []);
  return creators.sort((left, right) => left.name.localeCompare(right.name));
}

/** Static seed entries plus creators entered in Admin. Admin records win by name. */
export async function listCreators(): Promise<Creator[]> {
  const merged = new Map(getSeedCreators().map((creator) => [creator.name.toLowerCase(), creator]));
  for (const creator of await listManagedCreators()) merged.set(creator.name.toLowerCase(), creator);
  return [...merged.values()].sort((left, right) => left.name.localeCompare(right.name));
}

export async function creatorDirectoryUpdatedAt(): Promise<string> {
  const managed = await listManagedCreators();
  const dates = [CREATORS_UPDATED_AT, ...managed.map((creator) => creator.lastChecked)].filter(Boolean).sort();
  return dates.at(-1) ?? CREATORS_UPDATED_AT;
}

export async function saveCreator(
  input: Creator & { id?: string },
): Promise<ManagedCreator> {
  const creators = await listManagedCreators();
  const id = input.id?.trim().slice(0, 80) || creatorId(input.name);
  if (!id) throw new Error("Creator name must contain letters or numbers");
  const record: ManagedCreator = {
    id,
    name: input.name,
    tagline: input.tagline,
    categories: input.categories,
    languages: input.languages,
    links: input.links,
    avatar: input.avatar,
    lastChecked: input.lastChecked,
    updatedAt: new Date().toISOString(),
  };
  const next = [...creators.filter((creator) => creator.id !== id), record];
  await kvSetJson(DIRECTORY_KEY, next);
  return record;
}

export async function deleteCreator(id: string): Promise<boolean> {
  const creators = await listManagedCreators();
  const next = creators.filter((creator) => creator.id !== id);
  if (next.length === creators.length) return false;
  await kvSetJson(DIRECTORY_KEY, next);
  return true;
}

export const creatorCategoryKeys = new Set(CREATOR_CATEGORIES.map((category) => category.key));
export const creatorPlatformKeys = new Set(PLATFORMS.map((platform) => platform.key));
