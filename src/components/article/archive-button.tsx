"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Archive } from "lucide-react";
import { setStoryArchivedAction } from "@/app/actions";
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
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  async function toggle() {
    const next = !archived;
    setArchived(next);
    startTransition(async () => {
      try {
        await setStoryArchivedAction(storyId, next);
        router.refresh();
      } catch {
        setArchived(!next);
      }
    });
  }

  return (
    <Button variant="ghost" onClick={toggle} disabled={disabled || pending} className="gap-2">
      <Archive className="h-4 w-4" />
      {archived ? "Restore" : "Archive"}
    </Button>
  );
}
