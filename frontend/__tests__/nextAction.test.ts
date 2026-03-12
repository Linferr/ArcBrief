import { describe, expect, it } from 'vitest';

import { buildOnboardingModel, pickTodayNextAction, type NextActionCandidate } from '../app/components/onboarding';
import type { RecentBrief, Topic } from '../app/components/api';

const topic = (overrides: Partial<Topic> = {}): Topic => ({
  id: 1,
  name: 'AI Daily',
  keywords: [],
  rss_sources: [],
  scrape_frequency_hours: 4,
  push_time: '08:00',
  push_channels: ['discord'],
  is_active: true,
  ...overrides,
});

const brief = (overrides: Partial<RecentBrief> = {}): RecentBrief => ({
  id: 10,
  topic_id: 1,
  topic_name: 'AI Daily',
  date: '2026-03-10',
  content: 'Brief content',
  item_count: 8,
  created_at: '2026-03-10T10:00:00Z',
  ...overrides,
});

describe('pickTodayNextAction', () => {
  it('prefers the brief with the broadest source coverage', () => {
    const picked = pickTodayNextAction(
      [
        { briefId: 1, topicId: 1, topicName: 'AI Daily', itemCount: 6, sourceCount: 9, clusterCount: 2, createdAt: '2026-03-10T08:00:00Z' },
        { briefId: 2, topicId: 2, topicName: 'Policy', itemCount: 12, sourceCount: 4, clusterCount: 3, createdAt: '2026-03-10T09:00:00Z' },
      ] satisfies NextActionCandidate[],
      new Date('2026-03-10T12:00:00Z'),
    );

    expect(picked?.briefId).toBe(1);
    expect(picked?.reason).toContain('broadest source coverage');
  });

  it('marks a candidate as weak signal when sources and items are both thin', () => {
    const picked = pickTodayNextAction(
      [
        { briefId: 3, topicId: 3, topicName: 'Builder', itemCount: 3, sourceCount: 2, clusterCount: 1, createdAt: '2026-03-10T11:00:00Z' },
      ],
      new Date('2026-03-10T12:00:00Z'),
    );

    expect(picked?.weakSignal).toBe(true);
  });
});

describe('buildOnboardingModel next action states', () => {
  it('keeps starter pack guidance when no topics exist', () => {
    const model = buildOnboardingModel([], []);
    expect(model.nextAction.kind).toBe('settings');
  });

  it('keeps refresh guidance when topics exist but briefs do not', () => {
    const model = buildOnboardingModel([topic()], []);
    expect(model.nextAction.kind).toBe('generate');
  });

  it('downgrades to open-brief when the best brief is still weak', () => {
    const recommendation = pickTodayNextAction([
      { briefId: 3, topicId: 1, topicName: 'AI Daily', itemCount: 3, sourceCount: 2, clusterCount: 1, createdAt: '2026-03-10T11:00:00Z' },
    ]);
    const model = buildOnboardingModel([topic()], [brief({ item_count: 3 })], recommendation);
    expect(model.nextAction.kind).toBe('open-brief');
  });

  it('recommends research when the best brief has enough evidence', () => {
    const recommendation = pickTodayNextAction([
      { briefId: 4, topicId: 1, topicName: 'AI Daily', itemCount: 12, sourceCount: 8, clusterCount: 3, createdAt: '2026-03-10T11:00:00Z' },
    ]);
    const model = buildOnboardingModel([topic()], [brief({ item_count: 12 })], recommendation);
    expect(model.nextAction.kind).toBe('research');
    if (model.nextAction.kind !== 'research') throw new Error('expected research next action');
    expect(model.nextAction.suggestedQuery).toContain('AI Daily');
    expect(model.nextAction.reason).toContain('broadest source coverage');
  });
});
