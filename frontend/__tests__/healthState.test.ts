import { describe, expect, it } from 'vitest';

import { computeDigestHealth, computeTopicHealth } from '../app/components/healthState';

describe('computeTopicHealth', () => {
  it('marks strong topic briefs as healthy', () => {
    expect(
      computeTopicHealth({
        sourceCount: 8,
        itemCount: 12,
        clusterCount: 3,
      }).kind,
    ).toBe('healthy');
  });

  it('marks thin topic briefs as low-signal', () => {
    expect(
      computeTopicHealth({
        sourceCount: 2,
        itemCount: 3,
        clusterCount: 1,
      }).kind,
    ).toBe('low-signal-day');
  });

  it('marks recent failures as generation-failed', () => {
    expect(
      computeTopicHealth({
        sourceCount: 0,
        itemCount: 0,
        clusterCount: 0,
        hadFailure: true,
      }).kind,
    ).toBe('generation-failed');
  });
});

describe('computeDigestHealth', () => {
  it('marks missing active topics as partial coverage', () => {
    expect(
      computeDigestHealth({
        activeTopicCount: 3,
        coveredTopicCount: 2,
        totalSourceCount: 12,
        totalItemCount: 20,
      }).kind,
    ).toBe('partial-coverage');
  });

  it('marks thin but complete digest cycles as low-signal', () => {
    expect(
      computeDigestHealth({
        activeTopicCount: 2,
        coveredTopicCount: 2,
        totalSourceCount: 4,
        totalItemCount: 6,
      }).kind,
    ).toBe('low-signal-day');
  });
});
