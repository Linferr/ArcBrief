'use client';

import { useEffect, useMemo, useState } from 'react';
import { apiFetch, downloadPdfResponse, markdownToPlainText, RecentBrief, Topic } from './api';

interface Props {
  topics: Topic[];
}

const formatBriefTime = (createdAt?: string, dateFallback?: string) => {
  if (createdAt) {
    return new Date(createdAt).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  }
  if (dateFallback) return dateFallback;
  return 'N/A';
};

export default function ArchivesPanel({ topics }: Props) {
  const [topicFilter, setTopicFilter] = useState<string>('all');
  const [items, setItems] = useState<RecentBrief[]>([]);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const [selectedBriefId, setSelectedBriefId] = useState<number | null>(null);

  const selectedBrief = useMemo(
    () => items.find((item) => item.id === selectedBriefId) || items[0] || null,
    [items, selectedBriefId]
  );

  const loadArchives = async (filter = topicFilter) => {
    setLoading(true);
    setNotice('');
    try {
      const suffix = filter === 'all' ? '' : `&topic_id=${filter}`;
      const res = await apiFetch(`/briefs/recent?limit=60${suffix}`);
      if (!res.ok) {
        setNotice('Failed to load archive.');
        setLoading(false);
        return;
      }
      const data = await res.json();
      const nextItems: RecentBrief[] = data.items || [];
      setItems(nextItems);
      if (nextItems.length > 0) {
        setSelectedBriefId((prev) => (prev && nextItems.some((x) => x.id === prev) ? prev : nextItems[0].id));
      } else {
        setSelectedBriefId(null);
      }
    } catch {
      setNotice('Failed to load archive.');
    }
    setLoading(false);
  };

  useEffect(() => {
    loadArchives(topicFilter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicFilter]);

  const exportBriefPdf = async (briefId: number) => {
    try {
      const res = await apiFetch(`/briefs/${briefId}/export/pdf`);
      const error = await downloadPdfResponse(res, `brief_${briefId}.pdf`);
      if (error) setNotice(error);
    } catch {
      setNotice('PDF export failed.');
    }
  };

  return (
    <section className="panel archives-panel">
      <div className="module-head">
        <h2>Brief Archive</h2>
        <p className="ui-font">Browse historical briefings across topics and export snapshots.</p>
      </div>

      <div className="archives-toolbar ui-font">
        <label>
          Topic
          <select value={topicFilter} onChange={(e) => setTopicFilter(e.target.value)}>
            <option value="all">All topics</option>
            {topics.map((topic) => (
              <option key={topic.id} value={String(topic.id)}>
                {topic.name}
              </option>
            ))}
          </select>
        </label>
        <button className="ghost" onClick={() => loadArchives(topicFilter)} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {notice && <div className="notice">{notice}</div>}

      <div className="archives-layout">
        <div className="card archives-list">
          <h4 className="section-eyebrow">Archive Index</h4>
          <div className="archives-items">
            {loading && <div className="muted">Loading...</div>}
            {!loading &&
              items.map((item) => (
                <button
                  key={item.id}
                  className={`archives-item ${selectedBrief?.id === item.id ? 'active' : ''}`}
                  onClick={() => setSelectedBriefId(item.id)}
                >
                  <div className="archives-item-title">{item.topic_name}</div>
                  <div className="archives-item-meta">
                    {item.item_count} items | {formatBriefTime(item.created_at, item.date)}
                  </div>
                </button>
              ))}
            {!loading && items.length === 0 && (
              <div className="muted">No archived briefs yet. Generate briefs from Daily Brief first.</div>
            )}
          </div>
        </div>

        <div className="card archives-preview">
          <div className="report-toolbar">
            <h4 className="section-eyebrow">Preview</h4>
            {selectedBrief && (
              <button className="ghost-link" onClick={() => exportBriefPdf(selectedBrief.id)}>
                Export PDF
              </button>
            )}
          </div>
          {selectedBrief ? (
            <div className="report-paper">
              <div className="report-paper-head ui-font">
                <span>{selectedBrief.topic_name}</span>
                <span>{formatBriefTime(selectedBrief.created_at, selectedBrief.date)}</span>
              </div>
              <pre className="brief-content">{markdownToPlainText(selectedBrief.content)}</pre>
            </div>
          ) : (
            <div className="muted">Select a brief to preview content.</div>
          )}
        </div>
      </div>
    </section>
  );
}
