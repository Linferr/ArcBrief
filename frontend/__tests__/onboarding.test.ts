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

describe('buildOnboardingModel', () => {
  it('asks the user to configure starter packs when no topics exist', () => {
    const model = buildOnboardingModel([], []);
    expect(model.nextAction.kind).toBe('settings');
    expect(model.steps[0].state).toBe('current');
    expect(model.steps[1].state).toBe('upcoming');
  });

  it('asks the user to generate the first brief when topics exist but briefs do not', () => {
    const model = buildOnboardingModel([topic()], []);
    expect(model.nextAction.kind).toBe('generate');
    expect(model.steps[0].state).toBe('done');
    expect(model.steps[1].state).toBe('current');
    expect(model.steps[2].state).toBe('upcoming');
  });

  it('suggests a deep research action once a brief exists', () => {
    const recommendation = pickTodayNextAction([
      {
        briefId: 10,
        topicId: 1,
        topicName: 'AI Daily',
        itemCount: 12,
        sourceCount: 9,
        clusterCount: 4,
        createdAt: '2026-03-10T10:00:00Z',
      } satisfies NextActionCandidate,
    ]);
    const model = buildOnboardingModel([topic()], [brief()], recommendation);
    expect(model.nextAction.kind).toBe('research');
    if (model.nextAction.kind !== 'research') throw new Error('expected research action');
    expect(model.nextAction.topicName).toBe('AI Daily');
    expect(model.nextAction.suggestedQuery).toContain('AI Daily');
    expect(model.steps[0].state).toBe('done');
    expect(model.steps[1].state).toBe('done');
    expect(model.steps[2].state).toBe('current');
  });
});
