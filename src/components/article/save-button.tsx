"use client";

import { useState } from "react";
import { Bookmark } from "lucide-react";
import { Button } from "@/components/ui/button";

export function SaveButton({
  storyId,
  initialSaved,
  disabled = false,
}: {
  storyId: string;
  initialSaved: boolean;
  disabled?: boolean;
}) {
  const [saved, setSaved] = useState(initialSaved);
  const [pending, setPending] = useState(false);

  async function toggle() {
    setPending(true);
    const next = !saved;
    setSaved(next);

    try {
      await fetch(`/api/stories/${storyId}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ saved: next }),
      });
    } finally {
      setPending(false);
    }
  }

  return (
    <Button variant="secondary" onClick={toggle} disabled={disabled || pending} className="gap-2">
      <Bookmark className="h-4 w-4" />
      {saved ? "Saved" : "Save"}
    </Button>
  );
}
