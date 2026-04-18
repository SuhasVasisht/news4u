"use client";

import { useState } from "react";
import { CheckCheck } from "lucide-react";
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
  const [pending, setPending] = useState(false);

  async function toggle() {
    setPending(true);
    const next = !read;
    setRead(next);

    try {
      await fetch(`/api/stories/${storyId}/read`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ read: next }),
      });
    } finally {
      setPending(false);
    }
  }

  return (
    <Button variant="ghost" onClick={toggle} disabled={disabled || pending} className="gap-2">
      <CheckCheck className="h-4 w-4" />
      {read ? "Unread" : "Mark read"}
    </Button>
  );
}
