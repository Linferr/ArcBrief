'use client';

import { useEffect, useMemo, useState } from 'react';
import { apiFetch, downloadPdfResponse, markdownToPlainText, Topic, Brief, RecentBrief, Article } from './api';

interface Props {
  topics: Topic[];
  onNavigateSettings: () => void;
  onNavigateArchive: () => void;
  onSendToResearch?: (query: string) => void;
}

type ActiveTopicKey = number | 'all';
type RefreshPhase = 'idle' | 'collecting' | 'generating' | 'done';
type RenderedSource = { raw: string; title: string; source: string; date: string };
type RenderedBriefEntry = {
  topicTag: string;
  clusterLabel: string;
  headline: string;
  summary: string;
  takeaways: string[];
  sentiment: string;
  reliability: string;
  relatedArticles: number;
};
type ParsedBriefView = {
  entries: RenderedBriefEntry[];
  sources: RenderedSource[];
  fallbackText: string;
};

const _isBoilerplateLine = (line: string): boolean => {
  const normalized = line.trim().toLowerCase();
  if (!normalized) return true;
  return (
    normalized === 'daily brief' ||
    normalized === 'tldr' ||
    normalized === 'sources' ||
    normalized.startsWith('total:') ||
    normalized.startsWith('source:') ||
    normalized.startsWith('sources:') ||
    normalized === '---' ||
    /^\d{4}-\d{2}-\d{2}$/.test(normalized)
  );
};

const formatBriefTimestamp = (brief: Brief): string => {
  const ts = brief.created_at ? new Date(brief.created_at) : new Date(`${brief.date}T00:00:00`);
  return ts.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
};

const splitBriefContent = (content: string): { body: string; sources: string[] } => {
  const lines = (content || '').split('\n');
  const sourceHeaderIndex = lines.findIndex((line) => /^##\s+sources/i.test(line.trim()));
  const bodyLines = sourceHeaderIndex >= 0 ? lines.slice(0, sourceHeaderIndex) : lines;
  const sourceLines = sourceHeaderIndex >= 0 ? lines.slice(sourceHeaderIndex + 1) : [];
  const sources = sourceLines
    .map((line) => line.trim())
    .filter((line) => line.startsWith('- '))
    .map((line) => line.slice(2).trim())
    .filter(Boolean);

  return {
    body: bodyLines.join('\n').trim(),
    sources,
  };
};

const extractBriefPreview = (brief: Brief): { title: string; snippet: string } => {
  const { body } = splitBriefContent(brief.content || '');
  const lines = markdownToPlainText(body)
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => !_isBoilerplateLine(line));

  const title = lines.find((line) => line.length > 10 && line.length < 80) || `Daily Brief ${brief.date}`;
  const snippet = lines.find((line) => line.length > 42) || lines[1] || lines[0] || 'No summary available.';

  return {
    title: title.length > 56 ? `${title.slice(0, 56)}...` : title,
    snippet: snippet.length > 92 ? `${snippet.slice(0, 92)}...` : snippet,
  };
};

const toReadableBriefBody = (body: string): string => {
  const normalized = markdownToPlainText(body || '')
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => !_isBoilerplateLine(line))
    .join('\n')
    .trim();
  return normalized || 'No synthesized summary available yet. Try Refresh Brief to regenerate.';
};

const parseSourceLine = (raw: string): RenderedSource => {
  const text = (raw || '').trim();
  const match = text.match(/^(.*?)\s+\[(.*?)\]\s+\((\d{4}-\d{2}-\d{2})\)\s+\[(.*?)\]\s*$/);
  if (match) {
    return {
      raw: text,
      title: match[1].trim(),
      source: match[2].trim(),
      date: match[3].trim(),
    };
  }
  return { raw: text, title: text, source: '', date: '' };
};

const parseBriefView = (content: string): ParsedBriefView => {
  const { body, sources } = splitBriefContent(content || '');
  const sourceItems = sources.map(parseSourceLine);
  const lines = (body || '').split('\n');

  const entries: RenderedBriefEntry[] = [];
  let currentCluster = 'other';
  let current: RenderedBriefEntry | null = null;
  let mode: 'summary' | 'takeaways' = 'summary';

  const flush = () => {
    if (!current) return;
    current.summary = current.summary.trim() || 'No synthesized summary available yet.';
    if (!current.takeaways.length) current.takeaways = ['No additional verified signal.'];
    entries.push(current);
    current = null;
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line === '---') continue;

    const clusterMatch = line.match(/^##\s+\d+\.\s+(.+)$/i);
    if (clusterMatch) {
      flush();
      currentCluster = clusterMatch[1].trim() || 'other';
      mode = 'summary';
      continue;
    }

    const tagMatch = line.match(/^###\s+(.+)$/);
    if (tagMatch) {
      flush();
      current = {
        topicTag: tagMatch[1].trim(),
        clusterLabel: currentCluster,
        headline: '',
        summary: '',
        takeaways: [],
        sentiment: 'neutral',
        reliability: 'med',
        relatedArticles: 0,
      };
      mode = 'summary';
      continue;
    }

    if (!current) continue;

    if (/^\*\*key takeaways\*\*$/i.test(line)) {
      mode = 'takeaways';
      continue;
    }

    const boldLine = line.match(/^\*\*(.+)\*\*$/);
    if (boldLine) {
      const value = boldLine[1].trim();
      if (!/^key takeaways$/i.test(value) && !current.headline) {
        current.headline = value;
        continue;
      }
    }

    const sentimentLine = line.match(/^\*?sentiment:\s*([^|*]+)\|\s*reliability:\s*([^*]+)\*?$/i);
    if (sentimentLine) {
      current.sentiment = sentimentLine[1].trim().toLowerCase();
      current.reliability = sentimentLine[2].trim().toLowerCase();
      continue;
    }

    const relatedLine = line.match(/related articles:\s*(\d+)/i);
    if (relatedLine) {
      current.relatedArticles = Number(relatedLine[1]) || 0;
      continue;
    }

    if (mode === 'takeaways' && line.startsWith('- ')) {
      const item = line.slice(2).trim();
      if (item) current.takeaways.push(item);
      continue;
    }

    const cleaned = line.replace(/^>\s*/, '').trim();
    if (!_isBoilerplateLine(cleaned)) {
      current.summary = `${current.summary}${current.summary ? ' ' : ''}${cleaned}`;
    }
  }
  flush();

  return {
    entries,
    sources: sourceItems,
    fallbackText: toReadableBriefBody(body),
  };
};

export default function NewsFeedPanel({ topics, onNavigateSettings, onNavigateArchive }: Props) {
  const [activeTopic, setActiveTopic] = useState<ActiveTopicKey>('all');
  const [briefHistory, setBriefHistory] = useState<Brief[]>([]);
  const [allTopicBriefs, setAllTopicBriefs] = useState<RecentBrief[]>([]);
  const [topicArticles, setTopicArticles] = useState<Article[]>([]);
  const [articlesLoading, setArticlesLoading] = useState(false);
  const [selectedBriefId, setSelectedBriefId] = useState<number | null>(null);
  const [pendingBriefId, setPendingBriefId] = useState<number | null>(null);
  const [refreshPhase, setRefreshPhase] = useState<RefreshPhase>('idle');
  const [refreshStats, setRefreshStats] = useState<{ collected: number; saved: number; duplicates: number } | null>(null);
  const [notice, setNotice] = useState('');
  const [feedback, setFeedback] = useState<{ upvotes: number; downvotes: number } | null>(null);

  useEffect(() => {
    if (!topics.length) return;
    if (activeTopic === 'all') return;
    if (!topics.some((topic) => topic.id === activeTopic)) {
      setActiveTopic('all');
    }
  }, [topics, activeTopic]);

  const loadBriefHistory = async (topicId: number, preferredBriefId: number | null = null) => {
    try {
      const res = await apiFetch(`/briefs/${topicId}/history?limit=14`);
      if (res.ok) {
        const data = (await res.json()) as Brief[];
        setBriefHistory(data);
        if (data.length === 0) {
          setSelectedBriefId(null);
          return;
        }
        if (preferredBriefId && data.some((item) => item.id === preferredBriefId)) {
          setSelectedBriefId(preferredBriefId);
          return;
        }
        setSelectedBriefId(data[0].id);
      }
    } catch {
      setBriefHistory([]);
      setSelectedBriefId(null);
    }
  };

  const loadAllTopicBriefs = async () => {
    try {
      const res = await apiFetch('/briefs/recent?limit=200');
      if (!res.ok) {
        setAllTopicBriefs([]);
        return;
      }
      const data = (await res.json()) as { items: RecentBrief[] };
      const latestByTopic = new Map<number, RecentBrief>();
      for (const item of data.items || []) {
        if (!latestByTopic.has(item.topic_id)) latestByTopic.set(item.topic_id, item);
      }
      const merged = Array.from(latestByTopic.values()).sort((a, b) =>
        (a.topic_name || '').localeCompare(b.topic_name || '')
      );
      setAllTopicBriefs(merged);
    } catch {
      setAllTopicBriefs([]);
    }
  };

  const loadArticlesForBrief = async (topicId: number, date: string) => {
    setArticlesLoading(true);
    try {
      const res = await apiFetch(`/topics/${topicId}/articles?date=${encodeURIComponent(date)}&sort=time`);
      if (!res.ok) {
        setTopicArticles([]);
        return;
      }
      const data = (await res.json()) as { articles?: Article[] };
      setTopicArticles(data.articles || []);
    } catch {
      setTopicArticles([]);
    } finally {
      setArticlesLoading(false);
    }
  };

  useEffect(() => {
    if (activeTopic === 'all') {
      setBriefHistory([]);
      setSelectedBriefId(null);
      setTopicArticles([]);
      loadAllTopicBriefs();
      return;
    }
    if (typeof activeTopic === 'number') {
      loadBriefHistory(activeTopic, pendingBriefId);
      if (pendingBriefId) setPendingBriefId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTopic, pendingBriefId]);

  const selectedBrief = useMemo(
    () => briefHistory.find((brief) => brief.id === selectedBriefId) || briefHistory[0] || null,
    [briefHistory, selectedBriefId]
  );

  useEffect(() => {
    const brief = selectedBrief;
    if (brief) loadFeedback(brief.id);
    else setFeedback(null);
  }, [selectedBrief]);

  useEffect(() => {
    if (!selectedBrief) {
      setTopicArticles([]);
      return;
    }
    if (typeof activeTopic !== 'number') {
      setTopicArticles([]);
      return;
    }
    loadArticlesForBrief(activeTopic, selectedBrief.date);
  }, [selectedBrief, activeTopic]);

  const loadFeedback = async (briefId: number) => {
    try {
      const res = await apiFetch(`/briefs/${briefId}/feedback`);
      if (res.ok) setFeedback(await res.json());
    } catch {
      setFeedback(null);
    }
  };

  const submitFeedback = async (briefId: number, rating: number) => {
    try {
      const res = await apiFetch(`/briefs/${briefId}/feedback?rating=${rating}`, { method: 'POST' });
      if (res.ok) setFeedback(await res.json());
    } catch {}
  };

  const exportBriefPdf = async (briefId: number) => {
    try {
      const res = await apiFetch(`/briefs/${briefId}/export/pdf`);
      const error = await downloadPdfResponse(res, `brief_${briefId}.pdf`);
      if (error) setNotice(error);
    } catch {
      setNotice('PDF export failed.');
    }
  };

  const refreshAndGenerateAll = async () => {
    setRefreshPhase('collecting');
    setRefreshStats(null);
    setNotice('');
    try {
      const collectRes = await apiFetch('/topics/collect_all', { method: 'POST' });
      if (!collectRes.ok) {
        setNotice('Collection failed.');
        setRefreshPhase('idle');
        return;
      }
      const collectData = await collectRes.json();
      setRefreshStats({
        collected: collectData.total_collected || 0,
        saved: collectData.total_saved || 0,
        duplicates: collectData.total_duplicates || 0,
      });

      setRefreshPhase('generating');
      const briefRes = await apiFetch('/topics/brief_all', { method: 'POST' });
      if (!briefRes.ok) {
        setNotice('Brief generation failed.');
        setRefreshPhase('idle');
        return;
      }
      const briefData = await briefRes.json();
      setRefreshPhase('done');
      setNotice(`Updated ${briefData.total_topics} topics.`);

      if (activeTopic === 'all') {
        await loadAllTopicBriefs();
      } else if (typeof activeTopic === 'number') {
        await loadBriefHistory(activeTopic, selectedBriefId);
      }

      setTimeout(() => {
        setRefreshPhase('idle');
      }, 4000);
    } catch {
      setNotice('Refresh failed.');
      setRefreshPhase('idle');
    }
  };

  const activeTopicRecord = typeof activeTopic === 'number' ? topics.find((t) => t.id === activeTopic) || null : null;
  const isRefreshing = refreshPhase !== 'idle' && refreshPhase !== 'done';
  const selectedView = selectedBrief ? parseBriefView(selectedBrief.content || '') : null;
  const synthesisEntry = selectedView?.entries?.[0] || null;

  const compactSourceName = (source: string): string => {
    const raw = (source || '').trim();
    if (!raw) return 'Unknown Source';
    const cleaned = raw
      .replace(/["']/g, '')
      .replace(/\s*-\s*Newest:\s*.*$/i, '')
      .replace(/\s*[–-]\s*Breaking News.*$/i, '')
      .trim();
    return cleaned || raw;
  };

  const cleanArticleSnippet = (raw: string): string => {
    let text = markdownToPlainText(raw || '');
    text = text
      .replace(/article\s+url\s*:/gi, ' ')
      .replace(/comments?\s+url\s*:/gi, ' ')
      .replace(/points?\s*:\s*\d+/gi, ' ')
      .replace(/#\s*comments?\s*:\s*\d+/gi, ' ')
      .replace(/\[\s*publishedat\s*\]/gi, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    return text;
  };

  const formatArticleTime = (article: Article): string => {
    const raw = article.published_at || article.created_at;
    if (!raw) return 'Unknown time';
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw;
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  };

  return (
    <section className="panel panel-brief">
      <div className="module-head">
        <h2>Daily Briefing</h2>
        <p className="ui-font">
          {new Date().toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
          })}
        </p>
      </div>

      <div className="topic-cards-row brief-topic-row">
        <button key="all-topics" className={`topic-chip ${activeTopic === 'all' ? 'active' : ''}`} onClick={() => setActiveTopic('all')}>
          <span className="topic-chip-name">All Topics</span>
          {activeTopic === 'all' && <span className="topic-chip-dot" />}
        </button>

        {topics.map((topic) => {
          const isActive = activeTopic === topic.id;
          return (
            <button key={topic.id} className={`topic-chip ${isActive ? 'active' : ''}`} onClick={() => setActiveTopic(topic.id)}>
              <span className="topic-chip-name">{topic.name}</span>
              {isActive && <span className="topic-chip-dot" />}
            </button>
          );
        })}

        <button className="refresh-inline-btn ui-font" onClick={refreshAndGenerateAll} disabled={isRefreshing}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {isRefreshing ? (refreshPhase === 'collecting' ? 'Collecting...' : 'Generating...') : 'Refresh Brief'}
        </button>

        {topics.length === 0 && (
          <div className="card" style={{ textAlign: 'center', padding: '2rem' }}>
            <h3>Start Your News Feed</h3>
            <p className="muted">Create topics to track news by keywords and RSS sources.</p>
            <button onClick={onNavigateSettings} style={{ marginTop: '0.5rem' }}>Create Your First Topic</button>
          </div>
        )}
      </div>

      {activeTopic === 'all' && (
        <div className="card brief-card all-topics-card">
          <div className="brief-card-head">
            <div className="brief-title-group">
              <h3>All Topics Digest</h3>
              <span className="brief-subtitle">Latest brief from each topic</span>
            </div>
          </div>

          {allTopicBriefs.length === 0 && (
            <div className="muted">No topic briefs generated yet. Click Refresh Brief to generate one for each topic.</div>
          )}

          <div className="all-topics-stack">
            {allTopicBriefs.map((brief) => {
              const topic = topics.find((t) => t.id === brief.topic_id);
              const parsed = parseBriefView(brief.content || '');
              return (
                <article key={brief.id} className="all-topic-section">
                  <div className="all-topic-head">
                    <h4>{brief.topic_name || topic?.name || `Topic ${brief.topic_id}`}</h4>
                    <span className="source-meta">{formatBriefTimestamp(brief)}</span>
                  </div>

                  {parsed.entries.length > 0 ? (
                    <div className="brief-render-stack">
                      {parsed.entries.slice(0, 2).map((entry, idx) => (
                        <article key={`${brief.id}-entry-${idx}`} className="brief-article">
                          <div className="brief-article-head ui-font">
                            <div className="brief-article-meta">
                              <span className="brief-chip">{entry.topicTag || entry.clusterLabel}</span>
                              <span className="brief-meta-sep">|</span>
                              <span>{formatBriefTimestamp(brief)}</span>
                            </div>
                            <span className="brief-article-count">{entry.relatedArticles || brief.item_count} articles</span>
                          </div>
                          <h5 className="brief-headline">{entry.headline || entry.clusterLabel}</h5>
                          <p className="brief-summary">{entry.summary}</p>
                          <div className="brief-takeaways">
                            <div className="brief-takeaways-title ui-font">Key Takeaways</div>
                            <ul>
                              {entry.takeaways.slice(0, 2).map((takeaway, tIdx) => (
                                <li key={`${brief.id}-tk-${tIdx}`}>{takeaway}</li>
                              ))}
                            </ul>
                          </div>
                          <div className="brief-metadata ui-font">
                            <span className="badge">Sentiment: {entry.sentiment}</span>
                            <span className="badge">Reliability: {entry.reliability}</span>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <pre className="brief-content">{parsed.fallbackText}</pre>
                  )}

                  <div className="keyword-row">
                    <strong className="ui-font">Keywords:</strong>{' '}
                    {topic?.keywords?.length ? topic.keywords.join(', ') : 'N/A'}
                  </div>

                  {parsed.sources.length > 0 && (
                    <details className="brief-sources-details">
                      <summary className="ui-font">View Sources ({parsed.sources.length})</summary>
                      <ul className="brief-sources-list">
                        {parsed.sources.slice(0, 8).map((src, idx) => (
                          <li key={`${brief.id}-src-${idx}`}>
                            {src.source ? <strong>{src.source}: </strong> : null}
                            {src.title}
                            {src.date ? <span className="source-date"> ({src.date})</span> : null}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}

                  <div className="all-topic-actions">
                    <button
                      className="ghost"
                      onClick={() => {
                        setPendingBriefId(brief.id);
                        setActiveTopic(brief.topic_id);
                      }}
                    >
                      Open Topic Brief
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}

      {activeTopicRecord && (
        <div className="brief-layout">
          <div className="brief-main">
            {refreshPhase !== 'idle' && (
              <div className="refresh-banner">
                <div className="refresh-steps">
                  <div className={`refresh-step ${refreshPhase === 'collecting' ? 'active' : refreshPhase === 'generating' || refreshPhase === 'done' ? 'done' : ''}`}>
                    <span className="refresh-step-dot" />
                    <span>Collect</span>
                  </div>
                  <div className="refresh-step-line" />
                  <div className={`refresh-step ${refreshPhase === 'generating' ? 'active' : refreshPhase === 'done' ? 'done' : ''}`}>
                    <span className="refresh-step-dot" />
                    <span>Generate</span>
                  </div>
                  <div className="refresh-step-line" />
                  <div className={`refresh-step ${refreshPhase === 'done' ? 'done' : ''}`}>
                    <span className="refresh-step-dot" />
                    <span>Done</span>
                  </div>
                </div>
                {refreshStats && (
                  <div className="refresh-stats">
                    {refreshStats.collected} collected | {refreshStats.saved} new | {refreshStats.duplicates} duplicates
                  </div>
                )}
                {notice && refreshPhase === 'done' && <div className="refresh-stats">{notice}</div>}
              </div>
            )}

            {briefHistory.length > 0 && (
              <>
                <div className="card brief-card interactive-brief-card">
                  <div className="brief-card-head">
                    <div className="brief-title-group">
                      <h3>Synthesis Brief</h3>
                      {selectedBrief && <span className="brief-subtitle">{selectedBrief.date}</span>}
                    </div>
                  </div>

                  {selectedBrief && (
                    <>
                      <div className="brief-hover-actions">
                        <button className="feedback-btn up" onClick={() => submitFeedback(selectedBrief.id, 1)} aria-label="Like brief">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                            <path d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017a2 2 0 01-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095a.905.905 0 00-.905.905c0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
                          </svg>
                        </button>
                        <button className="feedback-btn down" onClick={() => submitFeedback(selectedBrief.id, -1)} aria-label="Dislike brief">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                            <path d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018c.163 0 .326.02.485.06L17 4m-7 10v5a2 2 0 002 2h.095c.5 0 .905-.405.905-.905 0-.714.211-1.412.608-2.006L17 13V4m-7 10h2" />
                          </svg>
                        </button>
                        {feedback && <span className="brief-score mono">{feedback.upvotes - feedback.downvotes}</span>}
                      </div>

                      {synthesisEntry ? (
                        <article className="brief-article">
                          <div className="brief-article-head ui-font">
                            <div className="brief-article-meta">
                              <span className="brief-chip">{synthesisEntry.topicTag || synthesisEntry.clusterLabel}</span>
                              <span className="brief-meta-sep">|</span>
                              <span>{formatBriefTimestamp(selectedBrief)}</span>
                            </div>
                            <span className="brief-article-count">{synthesisEntry.relatedArticles || selectedBrief.item_count} articles</span>
                          </div>
                          <h5 className="brief-headline">{synthesisEntry.headline || synthesisEntry.clusterLabel}</h5>
                          <p className="brief-summary">{synthesisEntry.summary}</p>
                          <div className="brief-takeaways">
                            <div className="brief-takeaways-title ui-font">Key Takeaways</div>
                            <ul>
                              {synthesisEntry.takeaways.slice(0, 2).map((takeaway, tIdx) => (
                                <li key={`${selectedBrief.id}-synthesis-${tIdx}`}>{takeaway}</li>
                              ))}
                            </ul>
                          </div>
                          <div className="brief-metadata ui-font">
                            <span className="badge">Sentiment: {synthesisEntry.sentiment}</span>
                            <span className="badge">Reliability: {synthesisEntry.reliability}</span>
                          </div>
                        </article>
                      ) : (
                        <pre className="brief-content">{selectedView?.fallbackText || 'No synthesized summary available yet.'}</pre>
                      )}

                      <div className="keyword-row">
                        <strong className="ui-font">Keywords:</strong>{' '}
                        {activeTopicRecord.keywords.length ? activeTopicRecord.keywords.join(', ') : 'N/A'}
                      </div>

                      {(selectedView?.sources?.length || 0) > 0 && (
                        <details className="brief-sources-details">
                          <summary className="ui-font">View Sources ({selectedView!.sources.length})</summary>
                          <ul className="brief-sources-list">
                            {selectedView!.sources.slice(0, 12).map((src, idx) => (
                              <li key={`src-${selectedBrief.id}-${idx}`}>
                                {src.source ? <strong>{src.source}: </strong> : null}
                                {src.title}
                                {src.date ? <span className="source-date"> ({src.date})</span> : null}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}

                      <div className="brief-footer-actions">
                        <button className="export-brief-btn" onClick={() => exportBriefPdf(selectedBrief.id)} title="Export as PDF">
                          Export PDF
                        </button>
                      </div>
                    </>
                  )}
                </div>

                <div className="articles-section">
                  <div className="articles-header">
                    <h3>Brief Cards</h3>
                    <div className="sort-control ui-font">
                      <span>{articlesLoading ? 'Loading...' : `${topicArticles.length} cards`}</span>
                    </div>
                  </div>

                  {articlesLoading && (
                    <div className="articles-grid">
                      <div className="article-card skeleton-card">
                        <div className="skeleton" style={{ height: '12px', width: '30%', marginBottom: '10px' }} />
                        <div className="skeleton" style={{ height: '24px', width: '90%', marginBottom: '8px' }} />
                        <div className="skeleton" style={{ height: '16px', width: '100%', marginBottom: '6px' }} />
                        <div className="skeleton" style={{ height: '16px', width: '85%' }} />
                      </div>
                    </div>
                  )}

                  {!articlesLoading && topicArticles.length > 0 && (
                    <div className="articles-grid">
                      {topicArticles.map((article) => {
                        const snippet = cleanArticleSnippet(article.content);
                        return (
                          <article key={article.id} className="article-card news-article">
                            <div className="article-source">{compactSourceName(article.source)}</div>
                            <h4 className="article-title">{article.title}</h4>
                            <p className="article-content">
                              {snippet
                                ? snippet.length > 230
                                  ? `${snippet.slice(0, 230)}...`
                                  : snippet
                                : 'No excerpt available.'}
                            </p>
                            <div className="article-footer">
                              <span className="article-time">{formatArticleTime(article)} | {article.time_source || 'published_at'}</span>
                              <div className="article-actions">
                                <a className="learn-more" href={article.url} target="_blank" rel="noreferrer">
                                  Learn More
                                </a>
                              </div>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  )}

                  {!articlesLoading && topicArticles.length === 0 && (
                    <div className="card brief-card">
                      <p className="muted">No source cards for this brief date yet.</p>
                    </div>
                  )}
                </div>
              </>
            )}

            {briefHistory.length === 0 && (
              <div className="card brief-card" style={{ textAlign: 'center', padding: '2rem' }}>
                <p className="muted">No briefs yet. Click &quot;Refresh Brief&quot; at the top to create your first brief.</p>
              </div>
            )}
          </div>

          <aside className="brief-sidebar">
            <h4>Recent Briefs (48h)</h4>
            <div className="source-list brief-history-list">
              {briefHistory.map((brief) => {
                const preview = extractBriefPreview(brief);
                return (
                  <button
                    key={brief.id}
                    className={`source-item brief-history-item ${brief.id === selectedBriefId ? 'active' : ''}`}
                    onClick={() => setSelectedBriefId(brief.id)}
                  >
                    <div className="source-name">{preview.title}</div>
                    <div className="source-sample">{preview.snippet}</div>
                    <div className="source-meta">{brief.item_count} items | {formatBriefTimestamp(brief)}</div>
                  </button>
                );
              })}
              {briefHistory.length === 0 && <div className="muted">No generated brief history yet.</div>}
            </div>
            <button className="ghost source-registry-btn" onClick={onNavigateArchive}>View Brief Archive</button>
          </aside>
        </div>
      )}
    </section>
  );
}
