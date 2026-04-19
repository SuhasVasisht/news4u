type CollectorScoringInput = {
  publishedAt: string | Date | null | undefined;
  trustScore: number;
  engagement?: Record<string, unknown> | null;
  symbols?: unknown[] | null;
  now?: Date;
};

function round(value: number) {
  return Math.round(value * 10000) / 10000;
}

export function collectorRecencyScore(publishedAt: string | Date | null | undefined, now = new Date()) {
  if (!publishedAt) {
    return 0.3;
  }

  const ageHours = Math.max((now.getTime() - +new Date(publishedAt)) / (60 * 60 * 1000), 0);
  return Math.max(0, 1 - Math.min(ageHours / 48, 1));
}

export function collectorEngagementScore(engagement?: Record<string, unknown> | null) {
  if (!engagement) {
    return 0;
  }

  if (typeof engagement.score === "number") {
    return Math.min(engagement.score / 500, 1);
  }

  if (typeof engagement.clicks === "number") {
    return Math.min(engagement.clicks / 2500, 1);
  }

  if (Array.isArray(engagement.linked_urls) && engagement.linked_urls.length > 0) {
    return 0.3;
  }

  return 0;
}

export function collectorImportanceScore({
  publishedAt,
  trustScore,
  engagement,
  symbols,
  now = new Date(),
}: CollectorScoringInput) {
  const engagementScore = collectorEngagementScore(engagement);
  const marketImpactScore = Array.isArray(symbols) && symbols.length > 0 ? 1 : 0;
  return round(
    collectorRecencyScore(publishedAt, now) * 0.35 +
      trustScore * 0.2 +
      0 * 0.2 +
      engagementScore * 0.1 +
      marketImpactScore * 0.15,
  );
}

export function collectorImportanceToArticleScore(input: CollectorScoringInput) {
  return round(collectorImportanceScore(input) * 10);
}
