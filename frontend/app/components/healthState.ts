export type HealthStateKind =
  | 'healthy'
  | 'partial-coverage'
  | 'low-signal-day'
  | 'generation-failed';

export type HealthState = {
  kind: HealthStateKind;
  label: string;
  reason: string;
};

type TopicHealthInput = {
  sourceCount: number;
  itemCount: number;
  clusterCount: number;
  hadFailure?: boolean;
};

type DigestHealthInput = {
  activeTopicCount: number;
  coveredTopicCount: number;
  totalSourceCount: number;
  totalItemCount: number;
  hadFailure?: boolean;
};

export function computeTopicHealth(input: TopicHealthInput): HealthState {
  if (input.hadFailure) {
    return {
      kind: 'generation-failed',
      label: 'Generation failed',
      reason: 'The latest generation attempt failed, so this brief may be missing or incomplete.',
    };
  }

  if (input.sourceCount < 3 && input.itemCount < 4) {
    return {
      kind: 'low-signal-day',
      label: 'Low-signal day',
      reason: 'This topic completed successfully, but the current cycle has too little verified signal to support a strong summary.',
    };
  }

  if (input.sourceCount < 5 || input.itemCount < 6 || input.clusterCount < 2) {
    return {
      kind: 'partial-coverage',
      label: 'Partial coverage',
      reason: 'This brief has usable information, but coverage is still thinner than a healthy full-cycle topic brief.',
    };
  }

  return {
    kind: 'healthy',
    label: 'Healthy',
    reason: 'This brief has enough sources and topic structure to be treated as a healthy cycle output.',
  };
}

export function computeDigestHealth(input: DigestHealthInput): HealthState {
  if (input.hadFailure) {
    return {
      kind: 'generation-failed',
      label: 'Generation failed',
      reason: 'The latest digest refresh failed, so the current digest may be stale or incomplete.',
    };
  }

  if (input.coveredTopicCount === 0) {
    return {
      kind: 'low-signal-day',
      label: 'Low-signal day',
      reason: 'There is not enough saved brief coverage to form a reliable cross-topic digest yet.',
    };
  }

  if (input.coveredTopicCount < input.activeTopicCount) {
    return {
      kind: 'partial-coverage',
      label: 'Partial coverage',
      reason: 'Some active topics are missing from the current digest, so coverage is incomplete.',
    };
  }

  const minHealthySources = Math.max(8, input.activeTopicCount * 4);
  const minHealthyItems = Math.max(10, input.activeTopicCount * 5);

  if (input.totalSourceCount < minHealthySources && input.totalItemCount < minHealthyItems) {
    return {
      kind: 'low-signal-day',
      label: 'Low-signal day',
      reason: 'All active topics are present, but the total signal volume is still unusually thin for this cycle.',
    };
  }

  return {
    kind: 'healthy',
    label: 'Healthy',
    reason: 'All active topics are represented and the current digest has enough breadth to be treated as healthy.',
  };
}

export function healthStateClassName(kind: HealthStateKind): string {
  switch (kind) {
    case 'healthy':
      return 'health-state-healthy';
    case 'partial-coverage':
      return 'health-state-partial';
    case 'low-signal-day':
      return 'health-state-low';
    case 'generation-failed':
      return 'health-state-failed';
    default:
      return 'health-state-neutral';
  }
}
