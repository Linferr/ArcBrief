import { RecentBrief, Topic } from './api';

export type OnboardingStepState = 'done' | 'current' | 'upcoming';

export type OnboardingStep = {
  key: 'topics' | 'brief' | 'deep-action';
  title: string;
  description: string;
  state: OnboardingStepState;
};

export type NextActionCandidate = {
  briefId: number;
  topicId: number;
  topicName: string;
  itemCount: number;
  sourceCount: number;
  clusterCount: number;
  createdAt?: string;
};

export type ScoredNextActionCandidate = NextActionCandidate & {
  score: number;
  reason: string;
  weakSignal: boolean;
};

export type NextAction =
  | {
      kind: 'settings';
      title: string;
      description: string;
      ctaLabel: string;
    }
  | {
      kind: 'generate';
      title: string;
      description: string;
      ctaLabel: string;
    }
  | {
      kind: 'research';
      title: string;
      description: string;
      ctaLabel: string;
      suggestedQuery: string;
      topicName: string;
      topicId: number;
      reason: string;
    }
  | {
      kind: 'open-brief';
      title: string;
      description: string;
      ctaLabel: string;
      topicName: string;
      topicId: number;
      reason: string;
    };

export type OnboardingModel = {
  headline: string;
  summary: string;
  steps: OnboardingStep[];
  nextAction: NextAction;
};

const sortBriefsDesc = (briefs: RecentBrief[]): RecentBrief[] =>
  [...briefs].sort((a, b) => {
    const aTime = new Date(a.created_at || `${a.date}T00:00:00`).getTime();
    const bTime = new Date(b.created_at || `${b.date}T00:00:00`).getTime();
    return bTime - aTime;
  });

export function pickTodayNextAction(
  candidates: NextActionCandidate[],
  now: Date = new Date(),
): ScoredNextActionCandidate | null {
  if (!candidates.length) return null;

  const scored = candidates.map((candidate) => {
    const createdAt = candidate.createdAt ? new Date(candidate.createdAt) : null;
    const ageMs = createdAt && !Number.isNaN(createdAt.getTime()) ? now.getTime() - createdAt.getTime() : 0;
    const ageHours = Math.max(0, ageMs / (1000 * 60 * 60));
    const freshnessPenalty = Math.min(ageHours, 48) / 8;
    const score = candidate.sourceCount * 3 + candidate.itemCount * 1.5 + candidate.clusterCount * 2 - freshnessPenalty;

    let reason = 'because it is the freshest complete brief available right now';
    if (candidate.sourceCount >= 8) {
      reason = 'because it has the broadest source coverage today';
    } else if (candidate.itemCount >= 10) {
      reason = 'because it aggregates the most items in the current cycle';
    } else if (candidate.clusterCount >= 3) {
      reason = 'because it surfaces multiple distinct signal clusters';
    }

    return {
      ...candidate,
      score,
      reason,
      weakSignal: candidate.sourceCount < 3 && candidate.itemCount < 4,
    };
  });

  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return b.itemCount - a.itemCount;
  });

  return scored[0];
}

export function buildOnboardingModel(
  topics: Topic[],
  briefs: RecentBrief[],
  recommendation: ScoredNextActionCandidate | null = null,
): OnboardingModel {
  const activeTopics = topics.filter((topic) => topic.is_active);
  const latestBrief = sortBriefsDesc(briefs)[0] || null;
  const hasTopics = activeTopics.length > 0;
  const hasBriefs = Boolean(latestBrief);

  const steps: OnboardingStep[] = [
    {
      key: 'topics',
      title: 'Set up focus topics',
      description: 'Import a starter pack or create your first monitoring topics.',
      state: hasTopics ? 'done' : 'current',
    },
    {
      key: 'brief',
      title: 'Generate the first brief',
      description: 'Create at least one digest or topic brief from your configured feeds.',
      state: hasBriefs ? 'done' : hasTopics ? 'current' : 'upcoming',
    },
    {
      key: 'deep-action',
      title: 'Follow up with analysis',
      description: 'Use the generated brief as a launch point for a question or deeper research.',
      state: hasBriefs ? 'current' : 'upcoming',
    },
  ];

  if (!hasTopics) {
    return {
      headline: 'Start with a preset intelligence scope',
      summary:
        'ArcBrief becomes useful only after you define what to monitor. Import a starter pack first, then generate your first brief.',
      steps,
      nextAction: {
        kind: 'settings',
        title: 'Apply a starter pack',
        description:
          'Choose a preset topic bundle so the system can begin collecting sources and generating a first digest.',
        ctaLabel: 'Open Settings',
      },
    };
  }

  if (!hasBriefs) {
    return {
      headline: 'Generate the first digest from your configured topics',
      summary:
        'Your focus topics are ready, but there is no saved brief yet. Run a refresh once to turn the current feeds into a usable daily brief.',
      steps,
      nextAction: {
        kind: 'generate',
        title: 'Generate your first brief',
        description:
          'Run a collection + brief cycle to produce the first digest. After that, ArcBrief can recommend a deeper follow-up action.',
        ctaLabel: 'Refresh Briefs',
      },
    };
  }

  const next = recommendation
    ? recommendation
    : {
        briefId: latestBrief!.id,
        topicId: latestBrief!.topic_id,
        topicName: latestBrief!.topic_name || 'current intelligence cycle',
        itemCount: latestBrief!.item_count,
        sourceCount: 0,
        clusterCount: 0,
        createdAt: latestBrief!.created_at,
        score: 0,
        weakSignal: true,
        reason: 'because it is the freshest complete brief available right now',
      };

  if (next.weakSignal) {
    return {
      headline: 'Read the latest brief before going deeper',
      summary:
        'ArcBrief has generated a brief, but the current signal is still thin. Review the brief first, then decide whether it is worth a deeper research run.',
      steps,
      nextAction: {
        kind: 'open-brief',
        title: `Review the latest ${next.topicName} brief`,
        description: `This brief is the best current candidate ${next.reason}, but the signal is still too thin for an immediate deep research jump.`,
        ctaLabel: 'Open Topic Brief',
        topicName: next.topicName,
        topicId: next.topicId,
        reason: next.reason,
      },
    };
  }

  const suggestedQuery = `What are the most actionable implications from the latest ${next.topicName} brief?`;
  return {
    headline: 'You have enough signal to start a deeper action',
    summary:
      'The latest briefs are strong enough to support a follow-up question. The shortest path to value now is to deepen one topic instead of changing configuration.',
    steps,
    nextAction: {
      kind: 'research',
      title: `Deepen the latest ${next.topicName} signal`,
      description: `Start with this topic ${next.reason}. The system already has enough evidence to justify a follow-up research pass.`,
      ctaLabel: 'Send to Research',
      suggestedQuery,
      topicName: next.topicName,
      topicId: next.topicId,
      reason: next.reason,
    },
  };
}
