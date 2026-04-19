"use server";

import { revalidatePath } from "next/cache";
import type { AppPreferences } from "@/lib/types";
import {
  clearToday,
  setSourceHidden,
  setStoryArchived,
  setStoryRead,
  setStorySaved,
  setTopicMuted,
  updatePreferences,
} from "@/lib/services/news-service";

function refreshAppShell() {
  revalidatePath("/", "layout");
  revalidatePath("/");
  revalidatePath("/saved");
  revalidatePath("/archived");
  revalidatePath("/catchup");
  revalidatePath("/sources");
  revalidatePath("/settings");
}

export async function setStoryReadAction(storyId: string, read: boolean) {
  const result = await setStoryRead(storyId, read);
  refreshAppShell();
  revalidatePath(`/story/${storyId}`);
  return result;
}

export async function setStorySavedAction(storyId: string, saved: boolean) {
  const result = await setStorySaved(storyId, saved);
  refreshAppShell();
  revalidatePath(`/story/${storyId}`);
  return result;
}

export async function setStoryArchivedAction(storyId: string, archived: boolean) {
  const result = await setStoryArchived(storyId, archived);
  refreshAppShell();
  revalidatePath(`/story/${storyId}`);
  return result;
}

export async function markStoryReadOnViewAction(storyId: string) {
  return setStoryReadAction(storyId, true);
}

export async function clearTodayAction() {
  const result = await clearToday();
  refreshAppShell();
  return result;
}

export async function updatePreferencesAction(input: AppPreferences) {
  const result = await updatePreferences(input);
  refreshAppShell();
  return result;
}

export async function setSourceHiddenAction(sourceId: string, hidden: boolean) {
  const result = await setSourceHidden(sourceId, hidden);
  revalidatePath("/", "layout");
  revalidatePath("/sources");
  return result;
}

export async function setTopicMutedAction(topicId: string, muted: boolean) {
  const result = await setTopicMuted(topicId, muted);
  revalidatePath("/", "layout");
  revalidatePath("/sources");
  return result;
}
