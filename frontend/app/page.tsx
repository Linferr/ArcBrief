'use client';

import { useEffect, useMemo, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000/api';

type RunEvent = { stage: string; message: string };
type RunSummary = { run_id: string; query: string; status: string; created_at?: string };

type Topic = {
  id: number;
  name: string;
  keywords: string[];
  rss_sources: string[];
  scrape_frequency_hours: number;
  push_time: string;
  push_channels: string[];
  is_active: boolean;
};

type Article = {
  id: number;
  topic_id: number;
  title: string;
  url: string;
  content: string;
  source: string;
  published_at: string | null;
  created_at: string;
};

type Brief = {
  id: number;
  topic_id: number;
  date: string;
  content: string;
  item_count: number;
};

const toCsv = (list: string[]) => list.join(', ');

const PIPELINE_STAGES = [
  { key: 'outline', label: 'Outline' },
  { key: 'search', label: 'Search' },
  { key: 'summary', label: 'Summary' },
  { key: 'host', label: 'Host Critique' },
  { key: 'reflection', label: 'Reflection' },
  { key: 'final', label: 'Final Format' },
  { key: 'error', label: 'Error' },
];

// Topic颜色
const TOPIC_COLORS = [
  { bg: '#fef3c7', border: '#f59e0b', text: '#92400e' },
  { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' },
  { bg: '#d1fae5', border: '#10b981', text: '#065f46' },
  { bg: '#fae8ff', border: '#d946ef', text: '#86198f' },
  { bg: '#fee2e2', border: '#ef4444', text: '#991b1b' },
  { bg: '#e0e7ff', border: '#6366f1', text: '#3730a3' },
];
const getTopicColor = (idx: number) => TOPIC_COLORS[idx % TOPIC_COLORS.length];

export default function Page() {
  const [panel, setPanel] = useState<'research' | 'news' | 'settings'>('research');

  // Research state
  const [query, setQuery] = useState('Latest AI policy shifts in the US and EU');
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState('idle');
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [report, setReport] = useState('');
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState<RunSummary | null>(null);
  const [fullReport, setFullReport] = useState('');
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);

  // News state
  const [topics, setTopics] = useState<Topic[]>([]);
  const [activeTopicId, setActiveTopicId] = useState<number | null>(null);
  const [articles, setArticles] = useState<Article[]>([]);
  const [latestBrief, setLatestBrief] = useState<Brief | null>(null);
  const [sortBy, setSortBy] = useState<'time' | 'title'>('time');
  const [notice, setNotice] = useState<string>('');
  const [loading, setLoading] = useState(false);

  // Settings state
  const [topicName, setTopicName] = useState('');
  const [topicKeywords, setTopicKeywords] = useState('');
  const [topicRss, setTopicRss] = useState('');
  const [topicFrequency, setTopicFrequency] = useState(4);
  const [topicPushTime, setTopicPushTime] = useState('08:00');

  // ========== API ==========
  const loadHistory = async () => {
    try {
      const res = await fetch(`${API}/history`);
      if (res.ok) setHistory(await res.json());
    } catch {}
  };

  const loadTopics = async () => {
    try {
      const res = await fetch(`${API}/topics`);
      if (res.ok) {
        const data = await res.json();
        setTopics(data);
        if (data.length && activeTopicId === null) {
          setActiveTopicId(data[0].id);
        }
      }
    } catch {}
  };

  const loadArticles = async (topicId: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/topics/${topicId}/articles?hours=72&sort=${sortBy}`);
      if (res.ok) {
        const data = await res.json();
        setArticles(data.articles || []);
      }
    } catch {}
    setLoading(false);
  };

  const loadLatestBrief = async (topicId: number) => {
    try {
      const res = await fetch(`${API}/briefs/${topicId}/latest`);
      if (res.ok) {
        setLatestBrief(await res.json());
      } else {
        setLatestBrief(null);
      }
    } catch {
      setLatestBrief(null);
    }
  };

  useEffect(() => {
    loadHistory();
    loadTopics();
  }, []);

  useEffect(() => {
    if (activeTopicId !== null) {
      loadArticles(activeTopicId);
      loadLatestBrief(activeTopicId);
    }
  }, [activeTopicId, sortBy]);

  useEffect(() => {
    if (!runId) return;
    const timer = setInterval(async () => {
      const res = await fetch(`${API}/status/${runId}`);
      if (!res.ok) return;
      const data = await res.json();
      setStatus(data.status);
      setEvents(data.events || []);
      if (data.report_content) setReport(data.report_content);
      if (data.status === 'done') {
        clearInterval(timer);
        loadHistory();
      }
    }, 1400);
    return () => clearInterval(timer);
  }, [runId]);

  const startRun = async () => {
    setStatus('running');
    setReport('');
    setEvents([]);
    const res = await fetch(`${API}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    setRunId(data.run_id);
  };

  const openReport = async (run: RunSummary) => {
    setSelectedRun(run);
    setIsReportOpen(true);
    setReportLoading(true);
    setFullReport('');
    try {
      const res = await fetch(`${API}/report/${run.run_id}`);
      if (res.ok) {
        setFullReport(await res.text());
      } else {
        setFullReport('Report not found.');
      }
    } catch {
      setFullReport('Report load failed.');
    }
    setReportLoading(false);
  };

  const closeReport = () => {
    setIsReportOpen(false);
    setSelectedRun(null);
    setFullReport('');
  };

  const createTopic = async () => {
    if (!topicName.trim()) {
      setNotice('Please enter a topic name.');
      return;
    }
    setNotice('');
    const payload = {
      name: topicName.trim(),
      keywords: topicKeywords ? topicKeywords.split(',').map(k => k.trim()).filter(Boolean) : [],
      rss_sources: topicRss ? topicRss.split(',').map(r => r.trim()).filter(Boolean) : [],
      scrape_frequency_hours: topicFrequency,
      push_time: topicPushTime,
      push_channels: ['discord'],
    };
    try {
      const res = await fetch(`${API}/topics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        setNotice('Topic creation failed.');
        return;
      }
      const data = await res.json();
      await loadTopics();
      setActiveTopicId(data.id);
      setNotice('Topic created successfully!');
      // 清空表单
      setTopicName('');
      setTopicKeywords('');
      setTopicRss('');
    } catch (e) {
      setNotice('Topic creation failed.');
    }
  };

  const collectNow = async () => {
    if (!activeTopicId) return;
    setNotice('Collecting...');
    setLoading(true);
    try {
      const res = await fetch(`${API}/topics/${activeTopicId}/collect`, { method: 'POST' });
      if (!res.ok) {
        setNotice('Collect failed.');
        return;
      }
      const data = await res.json();
      setNotice(`Collected ${data.collected} items, saved ${data.saved}.`);
      await loadArticles(activeTopicId);
    } catch {
      setNotice('Collect failed.');
    }
    setLoading(false);
  };

  const generateBrief = async () => {
    if (!activeTopicId) return;
    setNotice('Generating brief...');
    setLoading(true);
    try {
      const res = await fetch(`${API}/topics/${activeTopicId}/brief`, { method: 'POST' });
      if (!res.ok) {
        setNotice('Brief generation failed.');
        return;
      }
      await loadLatestBrief(activeTopicId);
      setNotice('Brief updated.');
    } catch {
      setNotice('Brief generation failed.');
    }
    setLoading(false);
  };

  const deleteTopic = async (topicId: number) => {
    if (!confirm('Delete this topic?')) return;
    try {
      await fetch(`${API}/topics/${topicId}`, { method: 'DELETE' });
      await loadTopics();
      if (activeTopicId === topicId) {
        setActiveTopicId(topics.length > 1 ? topics.find(t => t.id !== topicId)?.id || null : null);
        setArticles([]);
        setLatestBrief(null);
      }
    } catch {}
  };

  const refreshAndGenerateAll = async () => {
    setNotice('Refreshing all topics...');
    setLoading(true);
    try {
      const collectRes = await fetch(`${API}/topics/collect_all`, { method: 'POST' });
      if (!collectRes.ok) {
        setNotice('Refresh failed.');
        return;
      }
      const collectData = await collectRes.json();
      setNotice(`Collected for ${collectData.total_topics} topics. Generating briefs...`);

      const briefRes = await fetch(`${API}/topics/brief_all`, { method: 'POST' });
      if (!briefRes.ok) {
        setNotice('Brief generation failed.');
        return;
      }
      const briefData = await briefRes.json();
      setNotice(`Briefs updated for ${briefData.total_topics} topics.`);

      if (activeTopicId) {
        await loadArticles(activeTopicId);
        await loadLatestBrief(activeTopicId);
      }
    } catch {
      setNotice('Refresh failed.');
    }
    setLoading(false);
  };

  const stages = useMemo(() => events.map(e => e.stage), [events]);
  const stageNow = stages[stages.length - 1] || 'idle';
  const progress = Math.min(
    stages.filter(s => ['outline', 'search', 'summary', 'reflection', 'final'].includes(s)).length / 8,
    1
  );
  const hostProgress = Math.min(stages.filter(s => s === 'host').length / 4, 1);
  const stageCounts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const e of events) {
      map[e.stage] = (map[e.stage] || 0) + 1;
    }
    return map;
  }, [events]);

  const activeTopic = topics.find(t => t.id === activeTopicId) || null;

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <div className="eyebrow">ArcBrief Intelligence Desk</div>
          <h1>ArcBrief</h1>
        </div>
        <div className="nav">
          {['research', 'news', 'settings'].map(key => (
            <button
              key={key}
              className={`nav-pill ${panel === key ? 'active' : ''}`}
              onClick={() => setPanel(key as any)}
            >
              {key === 'research' ? 'Deep Research' : key === 'news' ? 'News Feed' : 'Settings'}
            </button>
          ))}
        </div>
      </header>

      <main className="layout">
        {/* ========== RESEARCH PANEL (保持原设计) ========== */}
        {panel === 'research' && (
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>Research Run</h2>
                <p>Ask a question. The agent will search, reflect, and draft a report.</p>
              </div>
              <div className="status-chip">Status: {status} · Stage: {stageNow}</div>
            </div>

            <div className="query-box">
              <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Enter research question" />
              <button onClick={startRun} disabled={status === 'running'}>
                {status === 'running' ? 'Running…' : 'Start Research'}
              </button>
            </div>

            <div className="grid-two">
              <div className="card">
                <h3>Pipeline Progress</h3>
                <div className="progress-row">
                  <span>Query Agent</span>
                  <div className="meter"><span style={{ width: `${progress * 100}%` }} /></div>
                </div>
                <div className="progress-row">
                  <span>Host Critique</span>
                  <div className="meter"><span style={{ width: `${hostProgress * 100}%` }} /></div>
                </div>
                <div className="pipeline-grid">
                  {PIPELINE_STAGES.map(stage => (
                    <div key={stage.key} className={`pipeline-chip ${stage.key === stageNow ? 'active' : ''}`}>
                      <span>{stage.label}</span>
                      <strong>{stageCounts[stage.key] || 0}</strong>
                    </div>
                  ))}
                </div>
                <div className="log">
                  {events.slice(-6).map((e, idx) => (
                    <div key={idx}>
                      <strong>[{e.stage}]</strong> {e.message}
                    </div>
                  ))}
                </div>
              </div>

              <div className="card report-card">
                <h3>Report Preview</h3>
                <div className="report-actions">
                  <button className="ghost" onClick={() => runId && openReport({ run_id: runId, query, status })} disabled={!runId}>
                    Full Report
                  </button>
                  {runId && (
                    <a className="ghost-link" href={`${API}/report/${runId}/download`} target="_blank" rel="noopener noreferrer">
                      Download
                    </a>
                  )}
                </div>
                {report ? (
                  <pre className="report-preview">{report.split('\n').slice(0, 22).join('\n')}</pre>
                ) : (
                  <div className="muted">No report yet.</div>
                )}
              </div>
            </div>

            <div className="card history">
              <h3>Recent Runs</h3>
              <div className="history-grid">
                {history.slice(0, 6).map(h => (
                  <div key={h.run_id} className="history-item">
                    <div>
                      <div className="history-title">{h.query}</div>
                      <div className="muted">{h.status}</div>
                    </div>
                    <div className="history-actions">
                      <button onClick={() => openReport(h)}>Full Report</button>
                      <a href={`${API}/report/${h.run_id}/download`} target="_blank" rel="noopener noreferrer">
                        Download
                      </a>
                    </div>
                  </div>
                ))}
                {history.length === 0 && <div className="muted">No research history yet.</div>}
              </div>
            </div>

            {isReportOpen && (
              <div className="report-modal">
                <div className="report-modal-content">
                  <div className="report-modal-header">
                    <div>
                      <div className="eyebrow">Full Report</div>
                      <h3>{selectedRun?.query || 'Report'}</h3>
                    </div>
                    <div className="report-modal-actions">
                      {selectedRun && (
                        <a href={`${API}/report/${selectedRun.run_id}/download`} target="_blank" rel="noopener noreferrer">
                          Download
                        </a>
                      )}
                      <button onClick={closeReport}>Close</button>
                    </div>
                  </div>
                  {reportLoading ? (
                    <div className="muted">Loading report...</div>
                  ) : (
                    <pre className="report-full">{fullReport || 'No report content.'}</pre>
                  )}
                </div>
              </div>
            )}
          </section>
        )}

        {/* ========== NEWS PANEL (新增) ========== */}
        {panel === 'news' && (
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>News Feed</h2>
                <p>Your personalized news aggregation. Click a topic to view articles.</p>
              </div>
              <div className="status-chip">
                {activeTopic ? `Topic: ${activeTopic.name}` : 'Select a topic'}
              </div>
            </div>

            {/* Topic Cards */}
            <div className="topic-cards-row">
              {topics.map((topic, idx) => {
                const color = getTopicColor(idx);
                const isActive = activeTopicId === topic.id;
                return (
                  <button
                    key={topic.id}
                    className={`topic-chip ${isActive ? 'active' : ''}`}
                    style={{
                      backgroundColor: isActive ? color.border : color.bg,
                      borderColor: color.border,
                      color: isActive ? '#fff' : color.text,
                    }}
                    onClick={() => setActiveTopicId(topic.id)}
                  >
                    {topic.name}
                  </button>
                );
              })}
              {topics.length === 0 && (
                <div className="muted">No topics yet. Go to Settings to create one.</div>
              )}
            </div>

            {activeTopic && (
              <>
                {/* Controls */}
                <div className="brief-controls">
                  <select value={sortBy} onChange={e => setSortBy(e.target.value as any)}>
                    <option value="time">Sort by Time</option>
                    <option value="title">Sort by Title</option>
                  </select>
                  <button onClick={refreshAndGenerateAll} disabled={loading}>
                    {loading ? 'Running...' : 'Refresh & Generate'}
                  </button>
                  <span className="notice">{notice}</span>
                </div>

                {/* Brief */}
                {latestBrief && (
                  <div className="card brief-card">
                    <h3>Daily Brief · {latestBrief.date}</h3>
                    <pre>{latestBrief.content}</pre>
                  </div>
                )}

                {/* Articles */}
                <div className="articles-section">
                  <h3>{articles.length} Articles</h3>
                  <div className="articles-grid">
                    {articles.map(article => (
                      <div key={article.id} className="article-card">
                        <div className="article-source">{article.source}</div>
                        <div className="article-title">{article.title}</div>
                        <div className="article-content">
                          {article.content?.slice(0, 120)}{article.content?.length > 120 ? '...' : ''}
                        </div>
                        <div className="article-footer">
                          <span className="article-time">
                            {article.published_at ? new Date(article.published_at).toLocaleDateString() : 'Recent'}
                          </span>
                          <a href={article.url} target="_blank" rel="noopener noreferrer" className="learn-more">
                            Learn More →
                          </a>
                        </div>
                      </div>
                    ))}
                    {articles.length === 0 && !loading && (
                      <div className="muted">No articles yet. Click Refresh to collect.</div>
                    )}
                  </div>
                </div>
              </>
            )}
          </section>
        )}

        {/* ========== SETTINGS PANEL ========== */}
        {panel === 'settings' && (
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>Settings</h2>
                <p>Manage your topics, RSS sources, and preferences.</p>
              </div>
              <div className="status-chip">SQLite · APScheduler · Local</div>
            </div>

            <div className="grid-two">
              <div className="card">
                <h3>Create Topic</h3>
                <div className="form">
                  <label>
                    Name *
                    <input value={topicName} onChange={e => setTopicName(e.target.value)} placeholder="e.g., AI Daily" />
                  </label>
                  <label>
                    Keywords (comma separated, optional)
                    <input value={topicKeywords} onChange={e => setTopicKeywords(e.target.value)} placeholder="AI, LLM, GPT" />
                  </label>
                  <label>
                    RSS Sources (comma separated, optional)
                    <textarea value={topicRss} onChange={e => setTopicRss(e.target.value)} rows={3} placeholder="https://hnrss.org/frontpage" />
                  </label>
                  <div className="inline">
                    <label>
                      Frequency (hours)
                      <input type="number" min={1} value={topicFrequency} onChange={e => setTopicFrequency(Number(e.target.value))} />
                    </label>
                    <label>
                      Push time
                      <input type="time" value={topicPushTime} onChange={e => setTopicPushTime(e.target.value)} />
                    </label>
                  </div>
                  <button onClick={createTopic}>Create Topic</button>
                  {notice && <div className="notice">{notice}</div>}
                </div>
              </div>

              <div className="card">
                <h3>Your Topics</h3>
                <div className="topic-list">
                  {topics.map((topic, idx) => {
                    const color = getTopicColor(idx);
                    return (
                      <div key={topic.id} className="topic-card" style={{ borderLeftColor: color.border }}>
                        <div>
                          <div className="topic-name">{topic.name}</div>
                          <div className="muted">{toCsv(topic.keywords) || 'No keywords'}</div>
                          <div className="muted">{topic.rss_sources.length} RSS · {topic.scrape_frequency_hours}h · {topic.push_time}</div>
                        </div>
                        <button className="delete-btn" onClick={() => deleteTopic(topic.id)}>×</button>
                      </div>
                    );
                  })}
                  {topics.length === 0 && <div className="muted">No topics yet.</div>}
                </div>
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
