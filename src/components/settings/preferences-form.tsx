"use client";

import { useState } from "react";
import type { AppPreferences } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { ToggleSwitch } from "@/components/ui/toggle-switch";

export function PreferencesForm({ initialValues }: { initialValues: AppPreferences }) {
  const [values, setValues] = useState(initialValues);
  const [saved, setSaved] = useState(false);

  async function persist(next: AppPreferences) {
    setValues(next);
    setSaved(false);

    await fetch("/api/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next),
    });

    setSaved(true);
  }

  return (
    <div className="surface rounded-[28px] p-6">
      <div className="mb-6">
        <p className="text-xs uppercase tracking-[0.28em] text-muted">Preferences</p>
        <h2 className="headline mt-2 text-3xl text-ink">Quiet defaults for a single-reader workflow.</h2>
      </div>

      <div className="space-y-5">
        <label className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-ink">Theme</p>
            <p className="text-sm text-muted">Choose the baseline theme used on first load.</p>
          </div>
          <select
            className="surface-strong rounded-full px-4 py-2 text-sm"
            value={values.theme}
            onChange={(event) =>
              void persist({
                ...values,
                theme: event.target.value as AppPreferences["theme"],
              })
            }
          >
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>

        <label className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-ink">Feed density</p>
            <p className="text-sm text-muted">Tighter cards for scanning or more breathing room for reading.</p>
          </div>
          <select
            className="surface-strong rounded-full px-4 py-2 text-sm"
            value={values.feedDensity}
            onChange={(event) =>
              void persist({
                ...values,
                feedDensity: event.target.value as AppPreferences["feedDensity"],
              })
            }
          >
            <option value="comfortable">Comfortable</option>
            <option value="compact">Compact</option>
          </select>
        </label>

        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-ink">Open original source in a new tab</p>
            <p className="text-sm text-muted">Preserve the current reading session while checking the source page.</p>
          </div>
          <ToggleSwitch
            checked={values.openOriginalInNewTab}
            label="Toggle open original source in new tab"
            onChange={(openOriginalInNewTab) =>
              void persist({
                ...values,
                openOriginalInNewTab,
              })
            }
          />
        </div>
      </div>

      <div className="mt-6 flex items-center justify-between">
        <p className="text-sm text-muted">{saved ? "Saved." : "Changes persist immediately."}</p>
        <Button variant="secondary" disabled>
          Account preferences
        </Button>
      </div>
    </div>
  );
}
