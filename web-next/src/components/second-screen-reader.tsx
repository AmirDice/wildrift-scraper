"use client";

import { DraftAssistant } from "@/components/draft-assistant";
import { SecondScreen } from "@/components/second-screen";

/**
 * The draft assistant, fed by the screen reader instead of by tapping.
 *
 * One front end, not two. The reader used to print its own list of bans and
 * picks beside the assistant, which meant a second place to render a draft,
 * a second place to fix when the board changed, and no suggestions or counter
 * build for anyone who came through this door. Now the reader fills the real
 * board and everything downstream of it -- pick suggestions, the enemy read,
 * the counter build -- works exactly as it does on /draft.
 */
export function SecondScreenReader() {
  return <DraftAssistant reader={(applyScan) => <SecondScreen onScan={applyScan} />} />;
}
