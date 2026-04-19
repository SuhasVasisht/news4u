"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { clearTodayAction } from "@/app/actions";
import { Button } from "@/components/ui/button";

export function ClearTodayButton({
  disabled,
  initialCleared,
}: {
  disabled: boolean;
  initialCleared: boolean;
}) {
  const [cleared, setCleared] = useState(initialCleared);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  async function clear() {
    startTransition(async () => {
      const result = await clearTodayAction();
      if (result.cleared) {
        setCleared(true);
      }
      router.refresh();
    });
  }

  return (
    <Button variant="secondary" onClick={clear} disabled={disabled || cleared || pending}>
      {cleared ? "Cleared" : "Clear Today"}
    </Button>
  );
}
