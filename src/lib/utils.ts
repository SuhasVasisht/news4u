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

function normalizeParagraphWhitespace(value: string) {
  return value
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/\n+/g, " ")
    .replace(/[ \t]+/g, " ")
    .trim();
}

function splitIntoSentences(value: string) {
  const matches = value.match(/[^.!?]+(?:[.!?]+|$)/g) ?? [];
  return matches.map((sentence) => sentence.trim()).filter(Boolean);
}

export function formatArticleBodyParagraphs(value: string) {
  const normalized = value.replace(/\r\n?/g, "\n").trim();
  if (!normalized) {
    return [];
  }

  if (/\n\s*\n/.test(normalized)) {
    return normalized
      .split(/\n\s*\n+/)
      .map((paragraph) => normalizeParagraphWhitespace(paragraph))
      .filter(Boolean);
  }

  if (normalized.includes("\n")) {
    return normalized
      .split(/\n+/)
      .map((paragraph) => normalizeParagraphWhitespace(paragraph))
      .filter(Boolean);
  }

  const sentences = splitIntoSentences(normalized);
  if (sentences.length <= 2) {
    return [normalizeParagraphWhitespace(normalized)];
  }

  const paragraphs: string[] = [];
  let current: string[] = [];
  let currentLength = 0;

  for (const sentence of sentences) {
    current.push(sentence);
    currentLength += sentence.length + 1;

    if (current.length >= 2 && currentLength >= 120) {
      paragraphs.push(current.join(" "));
      current = [];
      currentLength = 0;
    }
  }

  if (current.length > 0) {
    if (current.length === 1 && paragraphs.length > 0) {
      paragraphs[paragraphs.length - 1] = `${paragraphs[paragraphs.length - 1]} ${current[0]}`;
    } else {
      paragraphs.push(current.join(" "));
    }
  }

  return paragraphs.map((paragraph) => normalizeParagraphWhitespace(paragraph)).filter(Boolean);
}
