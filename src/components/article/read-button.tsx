"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { CheckCheck } from "lucide-react";
import { setStoryReadAction } from "@/app/actions";
import { Button } from "@/components/ui/button";

export function ReadButton({
  storyId,
  initialRead,
  disabled = false,
}: {
  storyId: string;
  initialRead: boolean;
  disabled?: boolean;
}) {
  const [read, setRead] = useState(initialRead);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  async function toggle() {
    const next = !read;
    setRead(next);
    startTransition(async () => {
      try {
        await setStoryReadAction(storyId, next);
        router.refresh();
      } catch {
        setRead(!next);
      }
    });
  }

  return (
    <Button variant="ghost" onClick={toggle} disabled={disabled || pending} className="gap-2">
      <CheckCheck className="h-4 w-4" />
      {read ? "Unread" : "Mark read"}
    </Button>
  );
}
