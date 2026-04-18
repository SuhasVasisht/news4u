import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatRelativeTime(value: string) {
  const date = new Date(value).getTime();
  const now = Date.now();
  const diffHours = Math.round((date - now) / (1000 * 60 * 60));

  if (Math.abs(diffHours) < 24) {
    return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(
      diffHours,
      "hour",
    );
  }

  const diffDays = Math.round(diffHours / 24);
  return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(
    diffDays,
    "day",
  );
}
