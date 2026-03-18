'use client';

import { useEffect, useMemo, useState } from 'react';
import { apiFetch, downloadPdfResponse, markdownToPlainText, Topic, Brief, RecentBrief, Article } from './api';
import MarkdownViewer from './MarkdownViewer';
import { computeDigestHealth, computeTopicHealth, healthStateClassName } from './healthState';
import { runBriefRefreshAll } from './briefRefresh';

interface Props {
  topics: Topic[];
  onNavigateSettings: () => void;
  onNavigateArchive: () => void;
  onSendToResearch?: (query: string, briefId?: number | null) => void;
  requestedTopicId?: number | null;
  requestedBriefId?: number | null;
  onRequestedTopicHandled?: () => void;
  refreshToken?: number;
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
  fallbackMarkdown: string;
};

const SOURCE_SECTION_RE = /^##\s+(sources|\u6765\u6e90\u7d22\u5f15|\u6765\u6e90|\u30bd\u30fc\u30b9\u7d22\u5f15|\u30bd\u30fc\u30b9)$/i;
const TAKEAWAYS_SECTION_RE = /^\*\*(key takeaways|\u5173\u952e\u8981\u70b9|\u8981\u70b9|\u91cd\u8981\u30dd\u30a4\u30f3\u30c8)\*\*$/i;
const TAKEAWAYS_LABEL_RE = /^(key takeaways|\u5173\u952e\u8981\u70b9|\u8981\u70b9|\u91cd\u8981\u30dd\u30a4\u30f3\u30c8)$/i;
const SENTIMENT_RELIABILITY_RE =
  /^\*?(?:sentiment|\u60c5\u7eea|\u30bb\u30f3\u30c1\u30e1\u30f3\u30c8):\s*([^|*]+)\|\s*(?:reliability|\u53ef\u4fe1\u5ea6|\u4fe1\u983c\u6027):\s*([^*]+)\*?$/i;
const RELATED_ARTICLES_RE = /(?:related articles|\u76f8\u5173\u6587\u7ae0|\u95a2\u9023\u8a18\u4e8b):\s*(\d+)/i;
const EVIDENCE_REFS_RE = /^\*?(?:evidence refs|evidence references|\u8bc1\u636e\u5f15\u7528|\u30a8\u30d3\u30c7\u30f3\u30b9\u53c2\u7167):\s*/i;
const SYNTHESIS_SECTION_RE = /^##\s+(Synthesis|\u{1F4CC}.*|\u4eca\u65e5\u6838\u5fc3.*)$/iu;
const CLUSTER_SECTION_RE = /^##\s+(\u{1F4C2}.*|\d+\.\s+.+|\u30c6\u30fc\u30de\u5225\u52d5\u5411.*)$/iu;
const INSIGHTS_SECTION_RE = /^##\s+\u{1F4A1}\s*(.*)$/iu;

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

const buildBriefFollowupQuery = (topicName: string, briefDate: string): string =>
  `Deepen the ${topicName} brief from ${briefDate}. Validate the key claims, pull the strongest primary sources, and highlight what changed since the brief.`;

const splitBriefContent = (content: string): { body: string; sources: string[] } => {
  const lines = (content || '').split('\n');
  const sourceHeaderIndex = lines.findIndex((line) => SOURCE_SECTION_RE.test(line.trim()));
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
  const dateOnlyMatch = text.match(/^(.*?)\s+\((\d{4}-\d{2}-\d{2})\)\s*$/);
  if (dateOnlyMatch) {
    return {
      raw: text,
      title: dateOnlyMatch[1].trim(),
      source: '',
      date: dateOnlyMatch[2].trim(),
    };
  }
  return { raw: text, title: text, source: '', date: '' };
};

const normalizeTitleForMatch = (value: string): string =>
  (value || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

export const parseBriefView = (content: string): ParsedBriefView => {
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

    const synthMatch = line.match(SYNTHESIS_SECTION_RE);
    if (synthMatch) {
      flush();
      currentCluster = '__synthesis__';
      mode = 'summary';
      continue;
    }

    const clusterMatch = line.match(CLUSTER_SECTION_RE);
    if (clusterMatch) {
      flush();
      currentCluster = clusterMatch[1].trim() || 'other';
      mode = 'summary';
      continue;
    }

    const insightsMatch = line.match(INSIGHTS_SECTION_RE);
    if (insightsMatch) {
      flush();
      currentCluster = insightsMatch[1].trim() || 'Insights';
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

    if (TAKEAWAYS_SECTION_RE.test(line)) {
      mode = 'takeaways';
      continue;
    }

    const boldLine = line.match(/^\*\*(.+)\*\*$/);
    if (boldLine) {
      const value = boldLine[1].trim();
      if (!TAKEAWAYS_LABEL_RE.test(value) && !current.headline) {
        current.headline = value;
        continue;
      }
    }

    const sentimentLine = line.match(SENTIMENT_RELIABILITY_RE);
    if (sentimentLine) {
      current.sentiment = sentimentLine[1].trim().toLowerCase();
      current.reliability = sentimentLine[2].trim().toLowerCase();
      continue;
    }

    const relatedLine = line.match(RELATED_ARTICLES_RE);
    if (relatedLine) {
      current.relatedArticles = Number(relatedLine[1]) || 0;
      continue;
    }

    if (EVIDENCE_REFS_RE.test(line)) {
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
    fallbackMarkdown: body,
  };
};

export default function NewsFeedPanel({
  topics,
  onNavigateSettings,
  onNavigateArchive,
  onSendToResearch,
  requestedTopicId = null,
  requestedBriefId = null,
  onRequestedTopicHandled,
  refreshToken = 0,
}: Props) {
  const allowAdminActions = process.env.NEXT_PUBLIC_ARCBRIEF_ENABLE_ADMIN_ACTIONS !== '0';
  const [activeTopic, setActiveTopic] = useState<ActiveTopicKey>('all');
  const [briefHistory, setBriefHistory] = useState<Brief[]>([]);
  const [recentBriefIndex, setRecentBriefIndex] = useState<RecentBrief[]>([]);
  const [topicArticles, setTopicArticles] = useState<Article[]>([]);
  const [articlesLoading, setArticlesLoading] = useState(false);
  const [selectedBriefId, setSelectedBriefId] = useState<number | null>(null);
  const [pendingBriefId, setPendingBriefId] = useState<number | null>(null);
  const [refreshPhase, setRefreshPhase] = useState<RefreshPhase>('idle');
  const [refreshStats, setRefreshStats] = useState<{ collected: number; saved: number; duplicates: number } | null>(null);
  const [notice, setNotice] = useState('');
  const [feedback, setFeedback] = useState<{ upvotes: number; downvotes: number } | null>(null);
  
  const activeTopics = useMemo(() => topics.filter((topic) => topic.is_active), [topics]);
  const activeTopicIdSet = useMemo(() => new Set(activeTopics.map((topic) => topic.id)), [activeTopics]);

  useEffect(() => {
    if (!activeTopics.length) return;
    if (activeTopic === 'all') return;
    if (!activeTopicIdSet.has(activeTopic)) {
      setActiveTopic('all');
    }
  }, [activeTopics, activeTopic, activeTopicIdSet]);

  const loadBriefHistory = async (topicId: number, preferredBriefId: number | null = null) => {
    try {
      const res = await apiFetch(`/briefs/${topicId}/history?limit=30&since_hours=168`);
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
        setRecentBriefIndex([]);
        return;
      }
      const data = (await res.json()) as { items: RecentBrief[] };
      setRecentBriefIndex(data.items || []);
    } catch {
      setRecentBriefIndex([]);
    }
  };

  const loadArticlesForBrief = async (topicId: number, date: string, sourceHints: RenderedSource[] = []) => {
    setArticlesLoading(true);
    try {
      const res = await apiFetch(`/topics/${topicId}/articles?date=${encodeURIComponent(date)}&sort=time`);
      if (!res.ok) {
        setTopicArticles([]);
        return;
      }
      const data = (await res.json()) as { articles?: Article[] };
      const dated = data.articles || [];
      if (dated.length > 0) {
        setTopicArticles(dated);
        return;
      }

      const hintDates = Array.from(
        new Set(
          sourceHints
            .map((src) => src.date)
            .filter((d) => Boolean(d) && d !== date),
        ),
      ).slice(0, 3);
      if (!hintDates.length) {
        setTopicArticles([]);
        return;
      }

      const byDate = await Promise.all(
        hintDates.map(async (d) => {
          const r = await apiFetch(`/topics/${topicId}/articles?date=${encodeURIComponent(d)}&sort=time`);
          if (!r.ok) return [] as Article[];
          const payload = (await r.json()) as { articles?: Article[] };
          return payload.articles || [];
        }),
      );
      const fallbackArticles = byDate.flat();
      if (!fallbackArticles.length) {
        setTopicArticles([]);
        return;
      }

      const hintTitleSet = new Set(
        sourceHints
          .map((s) => normalizeTitleForMatch(s.title))
          .filter(Boolean),
      );
      if (!hintTitleSet.size) {
        setTopicArticles(fallbackArticles.slice(0, 40));
        return;
      }

      const matched = fallbackArticles.filter((article) =>
        hintTitleSet.has(normalizeTitleForMatch(article.title)),
      );
      setTopicArticles((matched.length > 0 ? matched : fallbackArticles).slice(0, 40));
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
  }, [activeTopic, pendingBriefId]);

  const selectedBrief = useMemo(
    () => briefHistory.find((brief) => brief.id === selectedBriefId) || briefHistory[0] || null,
    [briefHistory, selectedBriefId]
  );

  useEffect(() => {
    if (!allowAdminActions) {
      setFeedback(null);
      return;
    }
    const brief = selectedBrief;
    if (brief) loadFeedback(brief.id);
    else setFeedback(null);
  }, [selectedBrief, allowAdminActions]);

  useEffect(() => {
    if (!selectedBrief) {
      setTopicArticles([]);
      return;
    }
    if (typeof activeTopic !== 'number') {
      setTopicArticles([]);
      return;
    }
    const parsedForFetch = parseBriefView(selectedBrief.content || '');
    loadArticlesForBrief(activeTopic, selectedBrief.date, parsedForFetch.sources || []);
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
    if (!allowAdminActions) return;
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
    if (!allowAdminActions) {
      setNotice('Admin actions are disabled in public demo mode.');
      return;
    }
    setRefreshPhase('collecting');
    setRefreshStats(null);
    setNotice('');
    try {
      const result = await runBriefRefreshAll();
      if (!result.ok) {
        setNotice(result.error || 'Refresh failed.');
        setRefreshPhase('idle');
        return;
      }
      setRefreshStats({
        collected: result.summary?.collected || 0,
        saved: result.summary?.saved || 0,
        duplicates: result.summary?.duplicates || 0,
      });

      setRefreshPhase('generating');
      setRefreshPhase('done');
      setNotice(`Updated ${result.summary?.totalTopics || 0} topics.`);

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

  const allTopicBriefs = useMemo(() => {
    const latestByTopic = new Map<number, RecentBrief>();
    for (const item of recentBriefIndex) {
      if (!activeTopicIdSet.has(item.topic_id)) continue;
      if (!latestByTopic.has(item.topic_id)) latestByTopic.set(item.topic_id, item);
    }
    return Array.from(latestByTopic.values()).sort((a, b) =>
      (a.topic_name || '').localeCompare(b.topic_name || ''),
    );
  }, [recentBriefIndex, activeTopicIdSet]);
  const visibleAllTopicBriefs = useMemo(
    () => allTopicBriefs.filter((brief) => activeTopicIdSet.has(brief.topic_id)),
    [allTopicBriefs, activeTopicIdSet],
  );
  const parsedRecentBriefs = useMemo(() => {
    const byId = new Map<number, ParsedBriefView>();
    for (const brief of recentBriefIndex) {
      byId.set(brief.id, parseBriefView(brief.content || ''));
    }
    return byId;
  }, [recentBriefIndex]);
  const parsedAllTopicBriefs = useMemo(() => {
    const byId = new Map<number, ParsedBriefView>();
    for (const brief of visibleAllTopicBriefs) {
      byId.set(brief.id, parsedRecentBriefs.get(brief.id) || parseBriefView(brief.content || ''));
    }
    return byId;
  }, [visibleAllTopicBriefs, parsedRecentBriefs]);
  const activeTopicRecord = typeof activeTopic === 'number' ? activeTopics.find((t) => t.id === activeTopic) || null : null;
  const isRefreshing = refreshPhase !== 'idle' && refreshPhase !== 'done';
  const selectedView = selectedBrief ? parseBriefView(selectedBrief.content || '') : null;
  const synthesisEntry = selectedView?.entries?.find(e => e.clusterLabel === '__synthesis__') || null;
  const clusterEntries = useMemo(
    () => (selectedView?.entries || []).filter((e) => e.clusterLabel !== '__synthesis__'),
    [selectedView],
  );
  const refreshFailed = notice.toLowerCase().includes('failed');
  const missingDigestTopics = useMemo(
    () => activeTopics.filter((topic) => !visibleAllTopicBriefs.some((brief) => brief.topic_id === topic.id)),
    [activeTopics, visibleAllTopicBriefs],
  );
  const digestHealth = useMemo(() => {
    const totalSourceCount = visibleAllTopicBriefs.reduce((sum, brief) => {
      const parsed = parsedAllTopicBriefs.get(brief.id);
      return sum + (parsed?.sources.length || 0);
    }, 0);
    const totalItemCount = visibleAllTopicBriefs.reduce((sum, brief) => sum + brief.item_count, 0);
    return computeDigestHealth({
      activeTopicCount: activeTopics.length,
      coveredTopicCount: visibleAllTopicBriefs.length,
      totalSourceCount,
      totalItemCount,
      hadFailure: refreshFailed && visibleAllTopicBriefs.length === 0,
    });
  }, [activeTopics.length, visibleAllTopicBriefs, parsedAllTopicBriefs, refreshFailed]);
  const selectedTopicHealth = useMemo(() => {
    if (!selectedBrief || !selectedView) return null;
    return computeTopicHealth({
      sourceCount: selectedView.sources.length,
      itemCount: selectedBrief.item_count,
      clusterCount: clusterEntries.length,
      hadFailure: refreshFailed && briefHistory.length === 0,
    });
  }, [selectedBrief, selectedView, clusterEntries.length, refreshFailed, briefHistory.length]);

  useEffect(() => {
    if (requestedTopicId == null) return;
    setPendingBriefId(requestedBriefId ?? null);
    setActiveTopic(requestedTopicId);
    onRequestedTopicHandled?.();
  }, [requestedTopicId, requestedBriefId, onRequestedTopicHandled]);

  useEffect(() => {
    if (refreshToken === 0) return;
    if (activeTopic === 'all') {
      loadAllTopicBriefs();
      return;
    }
    if (typeof activeTopic === 'number') {
      loadBriefHistory(activeTopic, selectedBriefId);
    }
  }, [refreshToken]);

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

  const cleanArticleSnippet = (raw: string, title?: string): string => {
    let text = markdownToPlainText(raw || '');
    text = text
      .replace(/article\s+url\s*:/gi, ' ')
      .replace(/comments?\s+url\s*:/gi, ' ')
      .replace(/points?\s*:\s*\d+/gi, ' ')
      .replace(/#\s*comments?\s*:\s*\d+/gi, ' ')
      .replace(/\[\s*publishedat\s*\]/gi, ' ')
      .replace(/feed did not provide article body\.?/gi, ' ')
      .replace(/source body is unavailable; summary uses headline-level evidence\.?/gi, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    const sentenceParts = text.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);
    if (sentenceParts.length >= 2 && sentenceParts[0].toLowerCase() === sentenceParts[1].toLowerCase()) {
      text = sentenceParts.slice(1).join(' ').trim();
    }
    const normalizedTitle = (title || '').trim().toLowerCase();
    const normalize = (v: string) => v.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
    const normalizedText = normalize(text);
    const normalizedTitleLoose = normalize(normalizedTitle);
    if (
      normalizedTitleLoose &&
      (
        normalizedText === normalizedTitleLoose ||
        normalizedText.startsWith(`${normalizedTitleLoose} `) ||
        normalizedTitleLoose.startsWith(normalizedText)
      )
    ) {
      return '';
    }
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
      <div className="module-head divider-soft pb-4">
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

        {activeTopics.map((topic) => {
          const isActive = activeTopic === topic.id;
          return (
            <button key={topic.id} className={`topic-chip ${isActive ? 'active' : ''}`} onClick={() => setActiveTopic(topic.id)}>
              <span className="topic-chip-name">{topic.name}</span>
              {isActive && <span className="topic-chip-dot" />}
            </button>
          );
        })}

      {allowAdminActions && (
        <button 
          className="ghost group" 
          style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '32px', padding: '0 12px', marginLeft: 'auto' }} 
          onClick={refreshAndGenerateAll} 
          disabled={isRefreshing}
        >
          <svg className="icon-line group-hover:stroke-[var(--text-primary)] transition-colors" style={{ width: '14px', height: '14px' }} viewBox="0 0 24 24" aria-hidden>
            <path d="M21 12a9 9 0 11-2.5-7.5" />
            <path d="M21 4.5v7.5h-7.5" />
            <path d="M17 9l-3-3m0 0l-3 3m3-3v8" opacity="0.5" strokeWidth="1"/> 
          </svg>
          <span style={{ fontSize: '12px', fontWeight: 500 }}>
            {isRefreshing ? (refreshPhase === 'collecting' ? 'Collecting...' : 'Generating...') : 'Refresh Brief'}
          </span>
        </button>
      )}

        {activeTopics.length === 0 && (
          <div className="card" style={{ textAlign: 'center', padding: '2rem', width: '100%' }}>
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
              <h3 style={{ fontFamily: 'var(--font-serif)' }}>All Topics Digest</h3>
              <span className="brief-subtitle">Latest brief from each topic</span>
            </div>
            {activeTopics.length > 0 && (
              <span className={`health-state-badge ${healthStateClassName(digestHealth.kind)}`}>
                {digestHealth.label}
              </span>
            )}
          </div>
          {activeTopics.length > 0 && (
            <div className="health-state-reason ui-font">
              {digestHealth.reason}
              {missingDigestTopics.length > 0 && (
                <span className="health-state-extra"> Missing topics: {missingDigestTopics.map((topic) => topic.name).join(', ')}.</span>
              )}
            </div>
          )}

          {visibleAllTopicBriefs.length === 0 && (
            <div className="muted">
              {refreshFailed
                ? 'Brief generation failed in the latest cycle. Click Refresh Brief to try again.'
                : 'No topic briefs generated yet. Click Refresh Brief to generate one for each topic.'}
            </div>
          )}

          <div className="all-topics-stack">
            {visibleAllTopicBriefs.map((brief) => {
              const topic = activeTopics.find((t) => t.id === brief.topic_id);
              const parsed = parsedAllTopicBriefs.get(brief.id) || parseBriefView(brief.content || '');
              const topicSynthesis = parsed.entries.find((e) => e.clusterLabel === '__synthesis__') || null;
              const topicHealth = computeTopicHealth({
                sourceCount: parsed.sources.length,
                itemCount: brief.item_count,
                clusterCount: parsed.entries.filter((e) => e.clusterLabel !== '__synthesis__').length,
              });
              return (
                <article key={brief.id} className="all-topic-section">
                  <div className="all-topic-head">
                    <div>
                      <h4 style={{ fontFamily: 'var(--font-serif)' }}>{brief.topic_name || topic?.name || `Topic ${brief.topic_id}`}</h4>
                      <div className="health-state-row">
                        <span className={`health-state-badge ${healthStateClassName(topicHealth.kind)}`}>{topicHealth.label}</span>
                        <span className="source-meta">{formatBriefTimestamp(brief)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="health-state-reason ui-font">{topicHealth.reason}</div>

                  {topicSynthesis ? (
                    <div className="brief-render-stack">
                      <article className="brief-article" style={{ borderLeftColor: 'var(--border-color)', paddingLeft: '16px' }}>
                        <div className="brief-article-head ui-font">
                          <div className="brief-article-meta">
                            <span className="brief-chip">{topicSynthesis.topicTag || 'Daily Executive Summary'}</span>
                            <span className="brief-meta-sep">|</span>
                            <span>{formatBriefTimestamp(brief)}</span>
                          </div>
                          <span className="brief-article-count">{topicSynthesis.relatedArticles || brief.item_count} articles</span>
                        </div>
                        <h5 className="brief-headline" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <svg className="icon-line" style={{ width: '18px', height: '18px', color: '#d97706', opacity: 0.8 }} viewBox="0 0 24 24"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" /></svg>
                          {topicSynthesis.headline || 'Daily Executive Summary'}
                        </h5>
                        <p className="brief-summary">{topicSynthesis.summary}</p>
                        <div className="brief-takeaways">
                          <div className="brief-takeaways-title ui-font">Key Takeaways</div>
                          <ul className="list-diamond">
                            {topicSynthesis.takeaways.slice(0, 8).map((takeaway, tIdx) => (
                              <li key={`${brief.id}-tk-${tIdx}`}>{takeaway}</li>
                            ))}
                          </ul>
                        </div>
                        <div className="brief-metadata ui-font">
                          <span className="badge">Sentiment: {topicSynthesis.sentiment}</span>
                          <span className="badge">Reliability: {topicSynthesis.reliability}</span>
                        </div>
                      </article>
                    </div>
                  ) : (
                    <MarkdownViewer content={parsed.fallbackMarkdown || parsed.fallbackText || ''} className="brief-content" />
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
                  <div className="brief-card-head divider-soft">
                    <div className="brief-title-group" style={{ marginBottom: '8px' }}>
                      <h3 style={{ fontFamily: 'var(--font-serif)' }}>Synthesis Brief</h3>
                      {selectedBrief && <span className="brief-subtitle">{selectedBrief.date}</span>}
                    </div>
                    {selectedTopicHealth && (
                      <span className={`health-state-badge ${healthStateClassName(selectedTopicHealth.kind)}`}>
                        {selectedTopicHealth.label}
                      </span>
                    )}
                  </div>
                  {selectedTopicHealth && (
                    <div className="health-state-reason ui-font">{selectedTopicHealth.reason}</div>
                  )}

                  {selectedBrief && (
                    <>
                      {allowAdminActions && (
                        <div className="brief-hover-actions">
                          <button className="feedback-btn up" onClick={() => submitFeedback(selectedBrief.id, 1)} aria-label="Like brief">
                            <svg viewBox="0 0 24 24" className="icon-line" aria-hidden>
                              <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path>
                            </svg>
                          </button>
                          <button className="feedback-btn down" onClick={() => submitFeedback(selectedBrief.id, -1)} aria-label="Dislike brief">
                            <svg viewBox="0 0 24 24" className="icon-line" aria-hidden>
                              <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"></path>
                            </svg>
                          </button>
                          {feedback && <span className="brief-score mono">{feedback.upvotes - feedback.downvotes}</span>}
                        </div>
                      )}

                      {synthesisEntry ? (
                        <article className="brief-article" style={{ borderLeft: 'none', paddingLeft: 0 }}>
                          <div className="brief-article-head ui-font">
                            <div className="brief-article-meta">
                              <span className="brief-chip">{synthesisEntry.topicTag || synthesisEntry.clusterLabel}</span>
                              <span className="brief-meta-sep">|</span>
                              <span>{formatBriefTimestamp(selectedBrief)}</span>
                            </div>
                            <span className="brief-article-count">{synthesisEntry.relatedArticles || selectedBrief.item_count} articles</span>
                          </div>
                          <h5 className="brief-headline" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <svg className="icon-line" style={{ width: '18px', height: '18px', color: '#d97706', opacity: 0.8 }} viewBox="0 0 24 24"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" /></svg>
                            {synthesisEntry.headline || synthesisEntry.clusterLabel}
                          </h5>
                          <p className="brief-summary">{synthesisEntry.summary}</p>
                          <div className="brief-takeaways">
                            <div className="brief-takeaways-title ui-font">Key Takeaways</div>
                            <ul className="list-diamond">
                              {synthesisEntry.takeaways.slice(0, 12).map((takeaway, tIdx) => (
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
                        <MarkdownViewer content={selectedView?.fallbackMarkdown || selectedView?.fallbackText || 'No synthesized summary available yet.'} className="brief-content" />
                      )}

                      {clusterEntries.length > 0 && (
                        <div className="brief-cluster-entries">
                          {clusterEntries.map((entry, eIdx) => (
                            <article key={`${selectedBrief.id}-cluster-${eIdx}`} className="brief-article">
                              <div className="brief-article-head ui-font">
                                <div className="brief-article-meta">
                                  <span className="brief-chip">{entry.topicTag}</span>
                                  {entry.clusterLabel !== 'other' && (
                                    <>
                                      <span className="brief-meta-sep">|</span>
                                      <span>{entry.clusterLabel}</span>
                                    </>
                                  )}
                                </div>
                              </div>
                              {entry.headline && <h5 className="brief-headline">{entry.headline}</h5>}
                              <p className="brief-summary">{entry.summary}</p>
                              {entry.takeaways.length > 0 && entry.takeaways[0] !== 'No additional verified signal.' && (
                                <div className="brief-takeaways">
                                  <div className="brief-takeaways-title ui-font">Key Takeaways</div>
                                  <ul className="list-diamond">
                                    {entry.takeaways.slice(0, 6).map((t, tIdx) => (
                                      <li key={`${selectedBrief.id}-c${eIdx}-tk-${tIdx}`}>{t}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </article>
                          ))}
                        </div>
                      )}

                      <div className="keyword-row mt-6">
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
                        <button
                          className="ghost"
                          onClick={() =>
                            onSendToResearch?.(
                              buildBriefFollowupQuery(activeTopicRecord.name, selectedBrief.date),
                              selectedBrief.id,
                            )
                          }
                        >
                          Research This Brief
                        </button>
                        <button className="export-brief-btn" onClick={() => exportBriefPdf(selectedBrief.id)} title="Export as PDF">
                          Export PDF
                        </button>
                      </div>
                    </>
                  )}
                </div>

                <div className="articles-section">
                  <div className="articles-header divider-soft pb-2">
                    <h3 style={{ fontFamily: 'var(--font-serif)' }}>Brief Cards</h3>
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
                        const snippet = cleanArticleSnippet(article.content, article.title);
                        return (
                          <article key={article.id} className="article-card news-article" style={{ borderLeftWidth: '3px' }}>
                            <div className="article-source">{compactSourceName(article.source)}</div>
                            <h4 className="article-title">{article.title}</h4>
                            <p className="article-content" style={{ fontFamily: 'var(--font-serif)' }}>
                              {snippet
                                ? snippet.length > 230
                                  ? `${snippet.slice(0, 230)}...`
                                  : snippet
                                : 'No excerpt available.'}
                            </p>
                            <div className="article-footer divider-soft border-t border-dashed pt-3 mt-4">
                              <span className="article-time">{formatArticleTime(article)} | {article.time_source || 'published_at'}</span>
                              <div className="article-actions">
                                <a className="learn-more flex items-center font-semibold" href={article.url} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
                                  Learn More
                                  <svg className="icon-line" style={{ width: '14px', height: '14px', marginLeft: '4px' }} viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
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
            <h4 className="ui-font">Recent Briefs (7d)</h4>
            <div className="source-list brief-history-list">
              {briefHistory.map((brief) => {
                const preview = extractBriefPreview(brief);
                return (
                  <button
                    key={brief.id}
                    className={`source-item brief-history-item ${brief.id === selectedBriefId ? 'active' : ''}`}
                    onClick={() => setSelectedBriefId(brief.id)}
                  >
                    <div className="source-name" style={{ fontFamily: 'var(--font-serif)' }}>{preview.title}</div>
                    <div className="source-sample">{preview.snippet}</div>
                    <div className="source-meta ui-font">{brief.item_count} items | {formatBriefTimestamp(brief)}</div>
                  </button>
                );
              })}
              {briefHistory.length === 0 && <div className="muted">No generated brief history yet.</div>}
            </div>
            <button className="ghost source-registry-btn flex items-center justify-center gap-1" onClick={onNavigateArchive}>
              View Brief Archive
              <svg className="icon-line" style={{ width: '14px', height: '14px' }} viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
            </button>
          </aside>
        </div>
      )}
    </section>
  );
}
