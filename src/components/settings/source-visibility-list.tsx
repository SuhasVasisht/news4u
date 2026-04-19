"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { setSourceHiddenAction } from "@/app/actions";
import type { ShellData } from "@/lib/types";
import { ToggleSwitch } from "@/components/ui/toggle-switch";

export function SourceVisibilityList({
  items,
}: {
  items: ShellData["sources"];
}) {
  const [sources, setSources] = useState(items);
  const [pendingId, startTransition] = useTransition();
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null);
  const router = useRouter();

  async function update(sourceId: string, hidden: boolean) {
    const previous = sources;
    setSources((current) =>
      current.map((item) => (item.id === sourceId ? { ...item, hidden } : item)),
    );
    setActiveSourceId(sourceId);
    startTransition(async () => {
      try {
        await setSourceHiddenAction(sourceId, hidden);
        router.refresh();
      } catch {
        setSources(previous);
      } finally {
        setActiveSourceId(null);
      }
    });
  }

  return (
    <div className="surface rounded-[28px] p-6">
      <div className="mb-6">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Source controls</p>
        <h2 className="headline mt-2 text-3xl text-ink">Strip out entire sources when they stop earning attention.</h2>
      </div>
      <div className="space-y-3">
        {sources.map((source) => (
          <div
            key={source.id}
            className="surface-strong flex items-center justify-between rounded-2xl px-4 py-4"
          >
            <div>
              <p className="text-sm font-medium text-ink">{source.name}</p>
              <p className="text-sm text-muted">{source.slug}</p>
            </div>
            <ToggleSwitch
              checked={!source.hidden}
              label={`Toggle ${source.name}`}
              disabled={pendingId && activeSourceId === source.id}
              onChange={(checked) => void update(source.id, !checked)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
