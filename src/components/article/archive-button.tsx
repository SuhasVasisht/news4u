"use client";

import { useState } from "react";
import { Archive } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ArchiveButton({
  storyId,
  initialArchived,
  disabled = false,
}: {
  storyId: string;
  initialArchived: boolean;
  disabled?: boolean;
}) {
  const [archived, setArchived] = useState(initialArchived);
  const [pending, setPending] = useState(false);

  async function toggle() {
    setPending(true);
    const next = !archived;
    setArchived(next);

    try {
      await fetch(`/api/stories/${storyId}/archive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: next }),
      });
    } finally {
      setPending(false);
    }
  }

  return (
    <Button variant="ghost" onClick={toggle} disabled={disabled || pending} className="gap-2">
      <Archive className="h-4 w-4" />
      {archived ? "Restore" : "Archive"}
    </Button>
  );
}
