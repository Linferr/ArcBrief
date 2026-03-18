import { describe, expect, it } from 'vitest';

import { buildRevisitRecommendations, type RevisitBriefCandidate } from '../app/components/revisit';

const frozenNow = new Date('2026-03-12T12:00:00Z');

const candidate = (overrides: Partial<RevisitBriefCandidate> = {}): RevisitBriefCandidate => ({
  briefId: 1,
  topicId: 1,
  topicName: 'AI Daily',
  date: '2026-03-11',
  createdAt: '2026-03-11T10:00:00Z',
  itemCount: 8,
  sourceCount: 6,
  clusterCount: 3,
  ...overrides,
});

describe('buildRevisitRecommendations', () => {
  it('returns no recommendations when each topic has only one brief', () => {
    const recs = buildRevisitRecommendations([candidate()]);
    expect(recs).toEqual([]);
  });

  it('prefers the prior brief when it has stronger evidence than the latest cycle', () => {
    const recs = buildRevisitRecommendations([
      candidate({
        briefId: 11,
        date: '2026-03-11',
        createdAt: '2026-03-11T10:00:00Z',
        itemCount: 4,
        sourceCount: 2,
        clusterCount: 1,
      }),
      candidate({
        briefId: 10,
        date: '2026-03-10',
        createdAt: '2026-03-10T10:00:00Z',
        itemCount: 12,
        sourceCount: 9,
        clusterCount: 4,
      }),
    ], frozenNow);

    expect(recs).toHaveLength(1);
    expect(recs[0].briefId).toBe(10);
    expect(recs[0].reason).toMatch(/stronger evidence/i);
  });

  it('skips revisit candidates older than seven days', () => {
    const recs = buildRevisitRecommendations([
      candidate({
        briefId: 11,
        date: '2026-03-11',
        createdAt: '2026-03-11T10:00:00Z',
      }),
      candidate({
        briefId: 10,
        date: '2026-03-01',
        createdAt: '2026-03-01T10:00:00Z',
      }),
    ], frozenNow);

    expect(recs).toEqual([]);
  });

  it('sorts recommendations by strongest revisit score across topics', () => {
    const recs = buildRevisitRecommendations([
      candidate({
        briefId: 21,
        topicId: 2,
        topicName: 'AI Policy & Safety',
        date: '2026-03-11',
        createdAt: '2026-03-11T09:00:00Z',
        itemCount: 6,
        sourceCount: 4,
        clusterCount: 2,
      }),
      candidate({
        briefId: 20,
        topicId: 2,
        topicName: 'AI Policy & Safety',
        date: '2026-03-10',
        createdAt: '2026-03-10T09:00:00Z',
        itemCount: 7,
        sourceCount: 5,
        clusterCount: 2,
      }),
      candidate({
        briefId: 11,
        topicId: 1,
        topicName: 'AI Daily',
        date: '2026-03-11',
        createdAt: '2026-03-11T10:00:00Z',
        itemCount: 4,
        sourceCount: 2,
        clusterCount: 1,
      }),
      candidate({
        briefId: 10,
        topicId: 1,
        topicName: 'AI Daily',
        date: '2026-03-10',
        createdAt: '2026-03-10T10:00:00Z',
        itemCount: 12,
        sourceCount: 9,
        clusterCount: 4,
      }),
    ], frozenNow);

    expect(recs).toHaveLength(2);
    expect(recs[0].topicName).toBe('AI Daily');
    expect(recs[1].topicName).toBe('AI Policy & Safety');
  });
});
