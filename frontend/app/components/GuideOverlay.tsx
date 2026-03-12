'use client';

import { useEffect, useMemo, useState } from 'react';
import { apiFetch, type RecentBrief, type StarterPack, type Topic } from './api';
import { runBriefRefreshAll } from './briefRefresh';
import { buildOnboardingModel, pickTodayNextAction, type NextActionCandidate } from './onboarding';
import { buildRevisitRecommendations, type RevisitBriefCandidate } from './revisit';
import { parseBriefView } from './NewsFeedPanel';

type Props = {
  topics: Topic[];
  deepActionStarted: boolean;
  onNavigateDailyBrief: () => void;
  onNavigateSettings: () => void;
  onNavigateArchive: () => void;
  onSendToResearch?: (query: string) => void;
  onOpenTopicBrief: (topicId: number, briefId?: number | null) => void;
  onRefreshCompleted?: () => void;
};

const GUIDE_PACK_KEY = 'guide_pack_completed';
const GUIDE_BRIEF_KEY = 'guide_brief_completed';
const GUIDE_DEEP_ACTION_KEY = 'guide_deep_action_completed';
const GUIDE_DISMISSED_KEY = 'guide_dismissed';

const readBool = (key: string): boolean => {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(key) === '1';
};

const writeBool = (key: string, value: boolean) => {
  if (typeof window === 'undefined') return;
  if (value) window.localStorage.setItem(key, '1');
  else window.localStorage.removeItem(key);
};

const packPreviewLine = (pack: StarterPack): string => {
  const topics = pack.topics.slice(0, 2).map((topic) => topic.name).join(', ');
  return topics ? `${pack.name} - ${topics}` : pack.name;
};

export default function GuideOverlay({
  topics,
  deepActionStarted,
  onNavigateDailyBrief,
  onNavigateSettings,
  onNavigateArchive,
  onSendToResearch,
  onOpenTopicBrief,
  onRefreshCompleted,
}: Props) {
  const allowAdminActions = process.env.NEXT_PUBLIC_ARCBRIEF_ENABLE_ADMIN_ACTIONS !== '0';
  const [recentBriefs, setRecentBriefs] = useState<RecentBrief[]>([]);
  const [starterPacks, setStarterPacks] = useState<StarterPack[]>([]);
  const [manualOpen, setManualOpen] = useState(false);
  const [forceWalkthrough, setForceWalkthrough] = useState(false);
  const [storageReady, setStorageReady] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [packCompleted, setPackCompleted] = useState(false);
  const [briefCompleted, setBriefCompleted] = useState(false);
  const [deepActionCompleted, setDeepActionCompleted] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState('');

  useEffect(() => {
    setDismissed(readBool(GUIDE_DISMISSED_KEY));
    setPackCompleted(readBool(GUIDE_PACK_KEY));
    setBriefCompleted(readBool(GUIDE_BRIEF_KEY));
    setDeepActionCompleted(readBool(GUIDE_DEEP_ACTION_KEY));
    setStorageReady(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [briefRes, packRes] = await Promise.all([
          apiFetch('/briefs/recent?limit=200'),
          apiFetch('/starter-packs'),
        ]);
        if (!cancelled && briefRes.ok) {
          const payload = (await briefRes.json()) as { items?: RecentBrief[] };
          setRecentBriefs(payload.items || []);
        }
        if (!cancelled && packRes.ok) {
          setStarterPacks((await packRes.json()) as StarterPack[]);
        }
      } catch {}
    };
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const activeTopics = useMemo(() => topics.filter((topic) => topic.is_active), [topics]);
  const activeTopicIdSet = useMemo(() => new Set(activeTopics.map((topic) => topic.id)), [activeTopics]);

  useEffect(() => {
    if (activeTopics.length === 0 || packCompleted) return;
    setPackCompleted(true);
    writeBool(GUIDE_PACK_KEY, true);
  }, [activeTopics.length, packCompleted]);

  useEffect(() => {
    if (recentBriefs.length === 0 || briefCompleted) return;
    setBriefCompleted(true);
    writeBool(GUIDE_BRIEF_KEY, true);
  }, [recentBriefs.length, briefCompleted]);

  useEffect(() => {
    if (!deepActionStarted || deepActionCompleted) return;
    setDeepActionCompleted(true);
    writeBool(GUIDE_DEEP_ACTION_KEY, true);
  }, [deepActionStarted, deepActionCompleted]);

  const visibleAllTopicBriefs = useMemo(() => {
    const latestByTopic = new Map<number, RecentBrief>();
    for (const item of recentBriefs) {
      if (!activeTopicIdSet.has(item.topic_id)) continue;
      if (!latestByTopic.has(item.topic_id)) latestByTopic.set(item.topic_id, item);
    }
    return Array.from(latestByTopic.values()).sort((a, b) =>
      (a.topic_name || '').localeCompare(b.topic_name || ''),
    );
  }, [recentBriefs, activeTopicIdSet]);

  const nextActionCandidate = useMemo(() => {
    const candidates: NextActionCandidate[] = visibleAllTopicBriefs.map((brief) => {
      const parsed = parseBriefView(brief.content || '');
      return {
        briefId: brief.id,
        topicId: brief.topic_id,
        topicName: brief.topic_name || `Topic ${brief.topic_id}`,
        itemCount: brief.item_count,
        sourceCount: parsed.sources.length,
        clusterCount: parsed.entries.filter((entry) => entry.clusterLabel !== '__synthesis__').length,
        createdAt: brief.created_at,
      };
    });
    return pickTodayNextAction(candidates);
  }, [visibleAllTopicBriefs]);

  const revisitRecommendations = useMemo(() => {
    const candidates: RevisitBriefCandidate[] = recentBriefs
      .filter((brief) => activeTopicIdSet.has(brief.topic_id))
      .map((brief) => {
        const parsed = parseBriefView(brief.content || '');
        return {
          briefId: brief.id,
          topicId: brief.topic_id,
          topicName: brief.topic_name || `Topic ${brief.topic_id}`,
          date: brief.date,
          createdAt: brief.created_at,
          itemCount: brief.item_count,
          sourceCount: parsed.sources.length,
          clusterCount: parsed.entries.filter((entry) => entry.clusterLabel !== '__synthesis__').length,
        };
      });
    return buildRevisitRecommendations(candidates);
  }, [recentBriefs, activeTopicIdSet]);

  const onboarding = useMemo(
    () => buildOnboardingModel(activeTopics, visibleAllTopicBriefs, nextActionCandidate),
    [activeTopics, visibleAllTopicBriefs, nextActionCandidate],
  );

  const allComplete = packCompleted && briefCompleted && deepActionCompleted;
  const showingWalkthrough = forceWalkthrough || !allComplete;
  const autoOpen = storageReady && !dismissed && showingWalkthrough;
  const isOpen = manualOpen || autoOpen;

  const openGuide = () => {
    setManualOpen(true);
    setRefreshNotice('');
  };

  const closeGuide = () => {
    setManualOpen(false);
    setForceWalkthrough(false);
    setDismissed(true);
    writeBool(GUIDE_DISMISSED_KEY, true);
  };

  const reopenWalkthrough = () => {
    setDismissed(false);
    writeBool(GUIDE_DISMISSED_KEY, false);
    setManualOpen(true);
    setForceWalkthrough(true);
  };

  const handleRefreshBriefs = async () => {
    setRefreshing(true);
    setRefreshNotice('');
    try {
      const result = await runBriefRefreshAll();
      if (!result.ok) {
        setRefreshNotice(result.error || 'Refresh failed.');
        return;
      }
      const res = await apiFetch('/briefs/recent?limit=200');
      if (res.ok) {
        const payload = (await res.json()) as { items?: RecentBrief[] };
        setRecentBriefs(payload.items || []);
      }
      onRefreshCompleted?.();
      setRefreshNotice(
        `Updated ${result.summary?.totalTopics || 0} topics | ${result.summary?.saved || 0} new items.`,
      );
    } finally {
      setRefreshing(false);
    }
  };

  const guideButtonVisible = storageReady && (dismissed || allComplete || !isOpen);

  return (
    <>
      {guideButtonVisible && (
        <button
          className="floating-guide-btn ui-font"
          onClick={openGuide}
          aria-label="Open guide"
          title="Guide / Compass"
        >
          <span aria-hidden>i</span>
          <span>Guide</span>
        </button>
      )}

      {isOpen && (
        <div className="guide-overlay-backdrop" role="presentation">
          <div className="guide-overlay-card" role="dialog" aria-modal="true" aria-label="Guide Overlay">
            <button className="guide-overlay-close ui-font" onClick={closeGuide} aria-label="Close guide">
              Close
            </button>

            {showingWalkthrough ? (
              <div className="guide-step-card">
                <div className="guide-step-kicker ui-font">Guide</div>
                <h3>{onboarding.nextAction.title}</h3>
                <p className="guide-step-summary">{onboarding.summary}</p>
                <div className="guide-step-status ui-font">
                  {onboarding.steps.filter((step) => step.state === 'done').length} / {onboarding.steps.length} complete
                </div>
                <div className="guide-step-list">
                  {onboarding.steps.map((step) => (
                    <div key={step.key} className={`guide-step-list-item guide-step-${step.state}`}>
                      <span className="guide-step-marker" aria-hidden>
                        {step.state === 'done' ? 'OK' : step.state === 'current' ? '>' : '-'}
                      </span>
                      <div>
                        <div className="guide-step-list-title ui-font">{step.title}</div>
                        <div className="guide-step-list-desc">{step.description}</div>
                      </div>
                    </div>
                  ))}
                </div>

                {!packCompleted && starterPacks.length > 0 && (
                  <div className="guide-pack-preview">
                    <div className="guide-pack-preview-title ui-font">Available starter packs</div>
                    <ul>
                      {starterPacks.slice(0, 3).map((pack) => (
                        <li key={pack.id}>{packPreviewLine(pack)}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {refreshNotice && <div className="guide-inline-notice ui-font">{refreshNotice}</div>}

                <div className="guide-step-actions">
                  {onboarding.nextAction.kind === 'settings' && (
                    <button className="paper-primary-btn" onClick={onNavigateSettings}>
                      {onboarding.nextAction.ctaLabel}
                    </button>
                  )}
                  {onboarding.nextAction.kind === 'generate' && (
                    <button
                      className="paper-primary-btn"
                      onClick={allowAdminActions ? handleRefreshBriefs : onNavigateDailyBrief}
                      disabled={refreshing}
                    >
                      {allowAdminActions
                        ? refreshing
                          ? 'Refreshing...'
                          : onboarding.nextAction.ctaLabel
                        : 'Open Daily Brief'}
                    </button>
                  )}
                  {onboarding.nextAction.kind === 'research' && (
                    <button
                      className="paper-primary-btn"
                      onClick={() => {
                        if (onboarding.nextAction.kind !== 'research') return;
                        onSendToResearch?.(onboarding.nextAction.suggestedQuery);
                      }}
                      disabled={!onSendToResearch}
                    >
                      {onboarding.nextAction.ctaLabel}
                    </button>
                  )}
                  {onboarding.nextAction.kind === 'open-brief' && (
                    <button
                      className="paper-primary-btn"
                      onClick={() => {
                        if (onboarding.nextAction.kind !== 'open-brief') return;
                        onOpenTopicBrief(onboarding.nextAction.topicId);
                      }}
                    >
                      {onboarding.nextAction.ctaLabel}
                    </button>
                  )}
                  <button className="ghost" onClick={onNavigateArchive}>
                    Open Archive
                  </button>
                </div>
              </div>
            ) : (
              <div className="guide-summary">
                <div className="guide-step-kicker ui-font">Compass</div>
                <h3>Guide & Next Actions</h3>
                <div className="guide-summary-section">
                  <div className="guide-summary-heading ui-font">Today&apos;s Next Action</div>
                  <h4>{onboarding.nextAction.title}</h4>
                  <p>{onboarding.nextAction.description}</p>
                  {onboarding.nextAction.kind === 'research' && (
                    <div className="guide-inline-query mono">{onboarding.nextAction.suggestedQuery}</div>
                  )}
                  <div className="guide-step-actions">
                    {onboarding.nextAction.kind === 'settings' && (
                      <button className="paper-primary-btn" onClick={onNavigateSettings}>
                        {onboarding.nextAction.ctaLabel}
                      </button>
                    )}
                    {onboarding.nextAction.kind === 'generate' && (
                      <button
                        className="paper-primary-btn"
                        onClick={allowAdminActions ? handleRefreshBriefs : onNavigateDailyBrief}
                        disabled={refreshing}
                      >
                        {allowAdminActions
                          ? refreshing
                            ? 'Refreshing...'
                            : onboarding.nextAction.ctaLabel
                          : 'Open Daily Brief'}
                      </button>
                    )}
                    {onboarding.nextAction.kind === 'research' && (
                      <>
                        <button
                          className="paper-primary-btn"
                          onClick={() => {
                            if (onboarding.nextAction.kind !== 'research') return;
                            onSendToResearch?.(onboarding.nextAction.suggestedQuery);
                          }}
                          disabled={!onSendToResearch}
                        >
                          {onboarding.nextAction.ctaLabel}
                        </button>
                        <button
                          className="ghost"
                          onClick={() => {
                            if (onboarding.nextAction.kind !== 'research') return;
                            onOpenTopicBrief(onboarding.nextAction.topicId);
                          }}
                        >
                          Open Topic Brief
                        </button>
                      </>
                    )}
                    {onboarding.nextAction.kind === 'open-brief' && (
                      <>
                        <button
                          className="paper-primary-btn"
                          onClick={() => {
                            if (onboarding.nextAction.kind !== 'open-brief') return;
                            onOpenTopicBrief(onboarding.nextAction.topicId);
                          }}
                        >
                          Open Topic Brief
                        </button>
                        <button
                          className="ghost"
                          onClick={allowAdminActions ? handleRefreshBriefs : () => {}}
                          disabled={refreshing || !allowAdminActions}
                        >
                          Refresh Briefs
                        </button>
                      </>
                    )}
                    <button className="ghost" onClick={onNavigateArchive}>
                      Open Archive
                    </button>
                  </div>
                </div>

                <div className="guide-summary-section">
                  <div className="guide-summary-heading ui-font">Revisit Queue</div>
                  {revisitRecommendations.length > 0 ? (
                    <div className="guide-revisit-list">
                      {revisitRecommendations.map((item) => (
                        <article key={item.briefId} className="guide-revisit-item">
                          <div className="guide-revisit-head">
                            <strong>{item.topicName}</strong>
                            <span className="ui-font">{item.date}</span>
                          </div>
                          <p>{item.reason}</p>
                          <div className="guide-step-actions">
                            <button
                              className="paper-primary-btn"
                              onClick={() => onOpenTopicBrief(item.topicId, item.briefId)}
                            >
                              Open Topic Brief
                            </button>
                            <button className="ghost" onClick={onNavigateArchive}>
                              Open Archive
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="guide-empty-copy">
                      No strong revisit candidate yet. Once a topic develops across multiple recent cycles, it will appear here.
                    </p>
                  )}
                </div>

                <div className="guide-summary-section">
                  <div className="guide-summary-heading ui-font">Guide</div>
                  <button className="ghost" onClick={reopenWalkthrough}>
                    Start Guide Again
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
