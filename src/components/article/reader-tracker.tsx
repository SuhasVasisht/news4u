"use client";

import { useEffect } from "react";

export function ReaderTracker({ storyId, initialRead }: { storyId: string; initialRead: boolean }) {
  useEffect(() => {
    if (initialRead) {
      return;
    }

    void fetch(`/api/stories/${storyId}/read`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ read: true }),
    });
  }, [storyId, initialRead]);

  return null;
}
