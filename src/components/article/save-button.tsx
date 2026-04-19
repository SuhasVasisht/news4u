"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Bookmark } from "lucide-react";
import { setStorySavedAction } from "@/app/actions";
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
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  async function toggle() {
    const next = !saved;
    setSaved(next);
    startTransition(async () => {
      try {
        await setStorySavedAction(storyId, next);
        router.refresh();
      } catch {
        setSaved(!next);
      }
    });
  }

  return (
    <Button variant="secondary" onClick={toggle} disabled={disabled || pending} className="gap-2">
      <Bookmark className="h-4 w-4" />
      {saved ? "Saved" : "Save"}
    </Button>
  );
}
