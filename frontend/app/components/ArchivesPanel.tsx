'use client';

import { useEffect, useMemo, useState } from 'react';
import { apiFetch, downloadPdfResponse, RecentBrief, Topic } from './api';
import MarkdownViewer from './MarkdownViewer';

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
      <div className="module-head divider-soft pb-4">
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

        <button 
          className="ghost group" 
          style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '32px', padding: '0 12px' }} 
          onClick={() => loadArchives(topicFilter)} 
          disabled={loading}
        >
          <svg className="icon-line group-hover:stroke-[var(--text-primary)] transition-colors" style={{ width: '14px', height: '14px' }} viewBox="0 0 24 24">
            <path d="M21 12a9 9 0 11-2.5-7.5" />
            <path d="M21 4.5v7.5h-7.5" />
          </svg>
          <span style={{ fontSize: '12px', fontWeight: 500 }}>{loading ? 'Refreshing...' : 'Refresh'}</span>
        </button>

      </div>

      {notice && <div className="notice">{notice}</div>}

      <div className="archives-layout">
        <div className="card archives-list">
          <h4 className="section-eyebrow">Archive Index</h4>
          <div className="archives-items">
            {loading && <div className="muted ui-font text-sm">Loading...</div>}
            {!loading &&
              items.map((item) => (
                <button
                  key={item.id}
                  className={`archives-item ${selectedBrief?.id === item.id ? 'active' : ''}`}
                  onClick={() => setSelectedBriefId(item.id)}
                >
                  <div className="archives-item-title" style={{ fontFamily: 'var(--font-serif)' }}>{item.topic_name}</div>
                  <div className="archives-item-meta ui-font">
                    {item.item_count} items | {formatBriefTime(item.created_at, item.date)}
                  </div>
                </button>
              ))}
            {!loading && items.length === 0 && (
              <div className="muted ui-font text-sm">No archived briefs yet. Generate briefs from Daily Brief first.</div>
            )}
          </div>
        </div>

        <div className="card archives-preview" style={{ padding: 0, border: 'none', background: 'transparent' }}>
          <div className="report-toolbar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h4 className="section-eyebrow" style={{ margin: 0 }}>Preview</h4>
            {selectedBrief && (

              <button 
                className="ghost group" 
                style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '32px', padding: '0 12px' }} 
                onClick={() => exportBriefPdf(selectedBrief.id)}
              >
                <svg className="icon-line group-hover:stroke-[var(--text-primary)] transition-colors" style={{ width: '14px', height: '14px' }} viewBox="0 0 24 24">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="7 10 12 15 17 10"></polyline>
                  <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                <span style={{ fontSize: '12px', fontWeight: 500 }}>Export PDF</span>
              </button>

            )}
          </div>
          {selectedBrief ? (
            <div className="report-paper">
              <div className="report-paper-head ui-font">
                <span style={{ fontFamily: 'var(--font-serif)', fontSize: '15px', fontWeight: 'bold', color: 'var(--text-primary)' }}>{selectedBrief.topic_name}</span>
                <span>{formatBriefTime(selectedBrief.created_at, selectedBrief.date)}</span>
              </div>
              <MarkdownViewer content={selectedBrief.content} />
            </div>
          ) : (
            <div className="muted" style={{ padding: '24px', background: 'var(--bg-sidebar)', border: '1px solid var(--border-color)', borderRadius: '4px' }}>Select a brief to preview content.</div>
          )}
        </div>
      </div>
    </section>
  );
}