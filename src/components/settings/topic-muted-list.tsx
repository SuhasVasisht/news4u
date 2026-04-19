"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { setTopicMutedAction } from "@/app/actions";
import type { ShellData } from "@/lib/types";
import { ToggleSwitch } from "@/components/ui/toggle-switch";

export function TopicMutedList({
  items,
}: {
  items: ShellData["topics"];
}) {
  const [topics, setTopics] = useState(items);
  const [pendingId, startTransition] = useTransition();
  const [activeTopicId, setActiveTopicId] = useState<string | null>(null);
  const router = useRouter();

  async function update(topicId: string, muted: boolean) {
    const previous = topics;
    setTopics((current) =>
      current.map((item) => (item.id === topicId ? { ...item, muted } : item)),
    );
    setActiveTopicId(topicId);
    startTransition(async () => {
      try {
        await setTopicMutedAction(topicId, muted);
        router.refresh();
      } catch {
        setTopics(previous);
      } finally {
        setActiveTopicId(null);
      }
    });
  }

  return (
    <div className="surface rounded-[28px] p-6">
      <div className="mb-6">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Topic controls</p>
        <h2 className="headline mt-2 text-3xl text-ink">Mute whole lanes when the signal-to-noise ratio drops.</h2>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {topics.map((topic) => (
          <div
            key={topic.id}
            className="surface-strong flex items-center justify-between rounded-2xl px-4 py-4"
          >
            <div>
              <p className="text-sm font-medium text-ink">{topic.name}</p>
              <p className="text-sm text-muted">{topic.storyCount} indexed stories</p>
            </div>
            <ToggleSwitch
              checked={!topic.muted}
              label={`Toggle ${topic.name}`}
              disabled={pendingId && activeTopicId === topic.id}
              onChange={(checked) => void update(topic.id, !checked)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
