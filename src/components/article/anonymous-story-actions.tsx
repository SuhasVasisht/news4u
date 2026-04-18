"use client";

import { useEffect, useState } from "react";
import { Archive, CheckCheck } from "lucide-react";
import { Button } from "@/components/ui/button";

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

function saveState(next: LocalState) {
  window.localStorage.setItem("anonymous-story-state", JSON.stringify(next));
  window.dispatchEvent(new CustomEvent("anonymous-story-state-changed"));
}

export function AnonymousStoryActions({ storyId }: { storyId: string }) {
  const [state, setState] = useState<LocalState>(defaultState);

  useEffect(() => {
    const onChange = () => setState(loadState());
    onChange();
    window.addEventListener("anonymous-story-state-changed", onChange);
    return () => window.removeEventListener("anonymous-story-state-changed", onChange);
  }, []);

  function toggle(kind: keyof LocalState) {
    const next = loadState();
    const current = new Set(next[kind]);
    if (current.has(storyId)) {
      current.delete(storyId);
    } else {
      current.add(storyId);
    }
    const updated = { ...next, [kind]: [...current] };
    setState(updated);
    saveState(updated);
  }

  const isRead = state.readStoryIds.includes(storyId);
  const isArchived = state.archivedStoryIds.includes(storyId);

  return (
    <>
      <Button variant="ghost" onClick={() => toggle("readStoryIds")} className="gap-2">
        <CheckCheck className="h-4 w-4" />
        {isRead ? "Unread" : "Mark read"}
      </Button>
      <Button variant="ghost" onClick={() => toggle("archivedStoryIds")} className="gap-2">
        <Archive className="h-4 w-4" />
        {isArchived ? "Restore" : "Archive"}
      </Button>
    </>
  );
}
