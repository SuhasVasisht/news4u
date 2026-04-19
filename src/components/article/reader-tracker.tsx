"use client";

import { useEffect } from "react";
import { markStoryReadOnViewAction } from "@/app/actions";

export function ReaderTracker({ storyId, initialRead }: { storyId: string; initialRead: boolean }) {
  useEffect(() => {
    if (initialRead) {
      return;
    }

    void markStoryReadOnViewAction(storyId);
  }, [storyId, initialRead]);

  return null;
}
