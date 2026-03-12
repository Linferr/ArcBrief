export type RevisitBriefCandidate = {
  briefId: number;
  topicId: number;
  topicName: string;
  date: string;
  createdAt?: string;
  itemCount: number;
  sourceCount: number;
  clusterCount: number;
};

export type RevisitRecommendation = RevisitBriefCandidate & {
  latestBriefId: number;
  latestDate: string;
  latestCreatedAt?: string;
  score: number;
  reason: string;
};

const toTime = (value?: string, dateFallback?: string): number => {
  const source = value || (dateFallback ? `${dateFallback}T00:00:00` : '');
  if (!source) return 0;
  const parsed = new Date(source).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
};

export function buildRevisitRecommendations(
  briefs: RevisitBriefCandidate[],
  now: Date = new Date(),
  limit = 3,
): RevisitRecommendation[] {
  const byTopic = new Map<number, RevisitBriefCandidate[]>();
  for (const brief of briefs) {
    const list = byTopic.get(brief.topicId) || [];
    list.push(brief);
    byTopic.set(brief.topicId, list);
  }

  const recommendations: RevisitRecommendation[] = [];

  for (const topicBriefs of byTopic.values()) {
    if (topicBriefs.length < 2) continue;
    const sorted = [...topicBriefs].sort(
      (a, b) => toTime(b.createdAt, b.date) - toTime(a.createdAt, a.date),
    );
    const latest = sorted[0];
    const prior = sorted[1];
    const priorAgeHours = Math.max(0, (now.getTime() - toTime(prior.createdAt, prior.date)) / (1000 * 60 * 60));

    if (priorAgeHours > 24 * 7) continue;
    if (prior.sourceCount < 2 && prior.itemCount < 4) continue;

    const score = prior.sourceCount * 2 + prior.itemCount + prior.clusterCount * 1.5 - priorAgeHours / 24;

    let reason = 'because this topic has developed across multiple recent cycles and merits a revisit';
    if (prior.sourceCount > latest.sourceCount + 1 || prior.itemCount > latest.itemCount + 2) {
      reason = 'because the prior brief still carries stronger evidence than the latest cycle';
    } else if (priorAgeHours <= 48) {
      reason = 'because it gives you the clearest baseline for comparing this topic’s latest shift';
    }

    recommendations.push({
      ...prior,
      latestBriefId: latest.briefId,
      latestDate: latest.date,
      latestCreatedAt: latest.createdAt,
      score,
      reason,
    });
  }

  return recommendations.sort((a, b) => b.score - a.score).slice(0, limit);
}
