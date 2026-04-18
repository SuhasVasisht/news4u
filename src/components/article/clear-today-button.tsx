"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

export function ClearTodayButton({
  disabled,
  initialCleared,
}: {
  disabled: boolean;
  initialCleared: boolean;
}) {
  const [cleared, setCleared] = useState(initialCleared);
  const [pending, setPending] = useState(false);
  const router = useRouter();

  async function clear() {
    setPending(true);
    try {
      await fetch("/api/feed/clear-today", { method: "POST" });
      setCleared(true);
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <Button variant="secondary" onClick={clear} disabled={disabled || cleared || pending}>
      {cleared ? "Cleared" : "Clear Today"}
    </Button>
  );
}
