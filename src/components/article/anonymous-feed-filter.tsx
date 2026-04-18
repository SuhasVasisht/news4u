"use client";

import { useEffect, useState } from "react";
import type { StoryCard } from "@/lib/types";
import { ArticleList } from "@/components/article/article-list";

type LocalState = {
  readStoryIds: string[];
  archivedStoryIds: string[];
  dismissedStoryIds: string[];
};

const defaultState: LocalState = {
  readStoryIds: [],
  archivedStoryIds: [],
  dismissedStoryIds: [],
};

function loadState() {
  try {
    const raw = window.localStorage.getItem("anonymous-story-state");
    if (!raw) {
      return defaultState;
    }
    return { ...defaultState, ...(JSON.parse(raw) as Partial<LocalState>) };
  } catch {
    return defaultState;
  }
}

export function AnonymousFeedFilter({
  items,
  emptyTitle,
  emptyCopy,
  storageKey,
}: {
  items: StoryCard[];
  emptyTitle: string;
  emptyCopy: string;
  storageKey: string;
}) {
  const [state, setState] = useState<LocalState>(defaultState);

  useEffect(() => {
    const onChange = () => setState(loadState());
    onChange();
    window.addEventListener("anonymous-story-state-changed", onChange);
    return () => window.removeEventListener("anonymous-story-state-changed", onChange);
  }, []);

  const hiddenIds = new Set([
    ...state.readStoryIds,
    ...state.archivedStoryIds,
    ...state.dismissedStoryIds,
  ]);
  const visible = items.filter((item) => !hiddenIds.has(item.id));

  return (
    <ArticleList
      items={visible}
      emptyTitle={emptyTitle}
      emptyCopy={emptyCopy}
      anonymousStateKey={storageKey}
    />
  );
}
