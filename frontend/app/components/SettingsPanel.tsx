'use client';

import { useEffect, useState } from 'react';
import { apiFetch, Topic, SystemStatus, RssHealthEntry, AppConfig, getTopicColor, toCsv } from './api';

interface Props {
  topics: Topic[];
  onTopicsChange: () => void;
}

type RunStat = {
  id: number;
  run_type: string;
  status: string;
  items_collected: number;
  items_saved: number;
  started_at: string;
};

export default function SettingsPanel({ topics, onTopicsChange }: Props) {
  const showDeveloperPanels = process.env.NEXT_PUBLIC_SHOW_DEV_PANELS === '1';
  const [topicName, setTopicName] = useState('');
  const [topicKeywords, setTopicKeywords] = useState('');
  const [topicRss, setTopicRss] = useState('');
  const [topicFrequency, setTopicFrequency] = useState(4);
  const [topicPushTime, setTopicPushTime] = useState('08:00');
  const [notice, setNotice] = useState('');

  // Edit state
  const [editingTopic, setEditingTopic] = useState<Topic | null>(null);
  const [editName, setEditName] = useState('');
  const [editKeywords, setEditKeywords] = useState('');
  const [editRss, setEditRss] = useState('');
  const [editFrequency, setEditFrequency] = useState(4);
  const [editPushTime, setEditPushTime] = useState('08:00');

  // System status
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);

  // RSS Health
  const [rssHealth, setRssHealth] = useState<RssHealthEntry[]>([]);
  const [healthExpanded, setHealthExpanded] = useState(false);
  const [appConfig, setAppConfig] = useState<AppConfig | null>(null);
  const [configSaving, setConfigSaving] = useState(false);
  const [runStats, setRunStats] = useState<RunStat[]>([]);
  const [runStatsTopicId, setRunStatsTopicId] = useState<number | null>(null);

  useEffect(() => {
    if (showDeveloperPanels) {
      apiFetch('/system/status').then(r => r.ok ? r.json() : null).then(d => d && setSystemStatus(d)).catch(() => {});
    }
    apiFetch('/rss-health').then(r => r.ok ? r.json() : null).then(d => d && setRssHealth(d.sources || [])).catch(() => {});
    apiFetch('/config').then(r => r.ok ? r.json() : null).then(d => d && setAppConfig(d)).catch(() => {});
  }, [showDeveloperPanels]);

  useEffect(() => {
    if (!showDeveloperPanels) return;
    if (topics.length === 0) {
      setRunStatsTopicId(null);
      return;
    }
    if (!runStatsTopicId || !topics.some((topic) => topic.id === runStatsTopicId)) {
      setRunStatsTopicId(topics[0].id);
    }
  }, [topics, runStatsTopicId, showDeveloperPanels]);

  useEffect(() => {
    if (!showDeveloperPanels) return;
    if (!runStatsTopicId) return;
    apiFetch(`/topics/${runStatsTopicId}/run-stats`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setRunStats(Array.isArray(data) ? data : []))
      .catch(() => setRunStats([]));
  }, [runStatsTopicId, showDeveloperPanels]);

  const createTopic = async () => {
    if (!topicName.trim()) { setNotice('Please enter a topic name.'); return; }
    setNotice('');
    try {
      const res = await apiFetch('/topics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: topicName.trim(),
          keywords: topicKeywords ? topicKeywords.split(',').map(k => k.trim()).filter(Boolean) : [],
          rss_sources: topicRss ? topicRss.split(',').map(r => r.trim()).filter(Boolean) : [],
          scrape_frequency_hours: topicFrequency,
          push_time: topicPushTime,
          push_channels: ['discord'],
        }),
      });
      if (!res.ok) { setNotice('Topic creation failed.'); return; }
      onTopicsChange();
      setNotice('Topic created successfully!');
      setTopicName(''); setTopicKeywords(''); setTopicRss('');
    } catch { setNotice('Topic creation failed.'); }
  };

  const deleteTopic = async (topicId: number) => {
    if (!confirm('Delete this topic?')) return;
    try {
      await apiFetch(`/topics/${topicId}`, { method: 'DELETE' });
      onTopicsChange();
    } catch {}
  };

  const startEdit = (topic: Topic) => {
    setEditingTopic(topic);
    setEditName(topic.name);
    setEditKeywords(topic.keywords.join(', '));
    setEditRss(topic.rss_sources.join(', '));
    setEditFrequency(topic.scrape_frequency_hours);
    setEditPushTime(topic.push_time);
  };

  const saveEdit = async () => {
    if (!editingTopic) return;
    const payload: Record<string, unknown> = {};
    if (editName.trim() !== editingTopic.name) payload.name = editName.trim();
    const newKw = editKeywords.split(',').map(k => k.trim()).filter(Boolean);
    if (JSON.stringify(newKw) !== JSON.stringify(editingTopic.keywords)) payload.keywords = newKw;
    const newRss = editRss.split(',').map(r => r.trim()).filter(Boolean);
    if (JSON.stringify(newRss) !== JSON.stringify(editingTopic.rss_sources)) payload.rss_sources = newRss;
    if (editFrequency !== editingTopic.scrape_frequency_hours) payload.scrape_frequency_hours = editFrequency;
    if (editPushTime !== editingTopic.push_time) payload.push_time = editPushTime;
    if (Object.keys(payload).length === 0) { setEditingTopic(null); return; }
    try {
      const res = await apiFetch(`/topics/${editingTopic.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) { setNotice('Topic updated.'); onTopicsChange(); }
      else setNotice('Update failed.');
    } catch { setNotice('Update failed.'); }
    setEditingTopic(null);
  };

  const saveConfig = async () => {
    if (!appConfig) return;
    setConfigSaving(true);
    setNotice('');
    try {
      const res = await apiFetch('/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(appConfig),
      });
      if (!res.ok) {
        setNotice('Configuration update failed.');
        setConfigSaving(false);
        return;
      }
      const data = await res.json();
      if (data?.config) setAppConfig(data.config);
      setNotice('Configuration saved.');
    } catch {
      setNotice('Configuration update failed.');
    }
    setConfigSaving(false);
  };

  return (
    <section className="panel settings-panel">
      <div className="module-head">
        <h2>Agent Protocol</h2>
        <p className="ui-font">System configuration and collection directives.</p>
      </div>

      <div className="settings-section">
        <h3 className="settings-section-title">Intelligence Scope</h3>
        <div className="grid-two settings-grid-scope">
          <div className="card">
            <h3>Focus Topics</h3>
            <div className="topic-list settings-topic-list">
              {topics.map((topic, idx) => {
                const color = getTopicColor(idx);
                const isEditing = editingTopic?.id === topic.id;
                return (
                  <div key={topic.id} className="topic-card" style={{ borderLeftColor: color.border }}>
                    {isEditing ? (
                      <div className="form" style={{ flex: 1, gap: '8px' }}>
                        <input value={editName} onChange={e => setEditName(e.target.value)} placeholder="Name" />
                        <input value={editKeywords} onChange={e => setEditKeywords(e.target.value)} placeholder="Keywords (comma separated)" />
                        <input value={editRss} onChange={e => setEditRss(e.target.value)} placeholder="RSS (comma separated)" />
                        <div className="inline">
                          <input type="number" min={1} value={editFrequency} onChange={e => setEditFrequency(Number(e.target.value))} />
                          <input type="time" value={editPushTime} onChange={e => setEditPushTime(e.target.value)} />
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <button className="paper-primary-btn" onClick={saveEdit}>Save</button>
                          <button className="ghost" onClick={() => setEditingTopic(null)}>Cancel</button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div>
                          <div className="topic-name">{topic.name}</div>
                          <div className="muted">{toCsv(topic.keywords) || 'No keywords'}</div>
                          <div className="muted">
                            {topic.rss_sources.length} RSS | every {topic.scrape_frequency_hours}h | push {topic.push_time}
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button className="delete-btn" style={{ borderColor: color.border, color: color.text }} onClick={() => startEdit(topic)}>&#9998;</button>
                          <button className="delete-btn" onClick={() => deleteTopic(topic.id)}>&times;</button>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
              {topics.length === 0 && <div className="muted" style={{ padding: '1rem', textAlign: 'center' }}>No topics yet. Use the form to create your first topic.</div>}
            </div>
          </div>

          <div className="card">
            <h3>Topic Intake</h3>
            <div className="form">
              <label>Name *<input value={topicName} onChange={e => setTopicName(e.target.value)} placeholder="e.g., AI Daily" /></label>
              <label>Keywords (comma separated, optional)<input value={topicKeywords} onChange={e => setTopicKeywords(e.target.value)} placeholder="AI, LLM, GPT" /></label>
              <label>RSS Sources (comma separated, optional)<textarea value={topicRss} onChange={e => setTopicRss(e.target.value)} rows={3} placeholder="https://hnrss.org/frontpage" /></label>
              <div className="inline">
                <label>Frequency (hours)<input type="number" min={1} value={topicFrequency} onChange={e => setTopicFrequency(Number(e.target.value))} /></label>
                <label>Push time<input type="time" value={topicPushTime} onChange={e => setTopicPushTime(e.target.value)} /></label>
              </div>
              <button className="paper-primary-btn" onClick={createTopic}>Create Topic</button>
              {notice && <div className="notice">{notice}</div>}
            </div>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <h3 className="settings-section-title">Agent Behavior</h3>
        <div className="card">
          {!appConfig && <div className="muted">Loading protocol configuration...</div>}
          {appConfig && (
            <>
              <div className="settings-toggle-row">
                <div>
                  <h4>Strict Academic Mode</h4>
                  <p className="muted ui-font">Exclude social media and forum sources for briefing and research.</p>
                </div>
                <input
                  type="checkbox"
                  checked={appConfig.strict_academic_mode}
                  onChange={(e) => setAppConfig({ ...appConfig, strict_academic_mode: e.target.checked })}
                />
              </div>
              <div className="settings-toggle-row">
                <div>
                  <h4>Critical Analysis Layer</h4>
                  <p className="muted ui-font">Force counter-arguments and contradiction checks in report drafting.</p>
                </div>
                <input
                  type="checkbox"
                  checked={appConfig.critical_analysis_layer}
                  onChange={(e) => setAppConfig({ ...appConfig, critical_analysis_layer: e.target.checked })}
                />
              </div>
              <label style={{ marginTop: '14px' }}>
                Priority Watchlist (Entities)
                <textarea
                  rows={3}
                  value={appConfig.entity_watchlist || ''}
                  placeholder="e.g. Sam Altman, TSMC 3nm, GPT-5"
                  onChange={(e) => setAppConfig({ ...appConfig, entity_watchlist: e.target.value })}
                />
              </label>
              <label style={{ marginTop: '14px' }}>
                Cognitive Model
                <select
                  value={appConfig.cognitive_model || 'Neutral (Fact-first)'}
                  onChange={(e) => setAppConfig({ ...appConfig, cognitive_model: e.target.value })}
                >
                  <option>Neutral (Fact-first)</option>
                  <option>Critique-heavy (Skeptic)</option>
                </select>
              </label>
              <button className="paper-primary-btn" onClick={saveConfig} disabled={configSaving} style={{ marginTop: '14px' }}>
                {configSaving ? 'Saving...' : 'Save Behavior & Watchlist'}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="settings-section">
        <h3 className="settings-section-title">System Connectors</h3>
      {appConfig && (
        <div className="card">
          <div className="inline">
            <label>
              Report Language
              <select
                value={appConfig.report_language}
                onChange={(e) => setAppConfig({ ...appConfig, report_language: e.target.value })}
              >
                <option>English (US)</option>
                <option>Chinese (Simplified)</option>
                <option>Japanese</option>
              </select>
            </label>
            <label>
              Primary LLM Model
              <select
                value={appConfig.primary_model}
                onChange={(e) => setAppConfig({ ...appConfig, primary_model: e.target.value })}
              >
                <option>Qwen3 MAX</option>
                <option>GPT-4o mini (OpenAI)</option>
                <option>GPT-4o (OpenAI)</option>
                <option>GPT-4.1 mini (OpenAI)</option>
                <option>Claude 3.5 Sonnet (Anthropic)</option>
                <option>Gemini 1.5 Pro (Google)</option>
              </select>
            </label>
          </div>
          <div className="inline" style={{ marginTop: '14px' }}>
            <label>
              Search Provider
              <select
                value={appConfig.search_provider}
                onChange={(e) => setAppConfig({ ...appConfig, search_provider: e.target.value })}
              >
                <option>Tavily Search API</option>
                <option>Serper (Google)</option>
                <option>Bing Search</option>
              </select>
            </label>
            <label>
              API Key Status
              <input value="Managed by environment variables" disabled />
            </label>
          </div>
          <button className="paper-primary-btn" onClick={saveConfig} disabled={configSaving} style={{ marginTop: '14px' }}>
            {configSaving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      )}

      {rssHealth.length > 0 && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3>Source Health</h3>
            <button className="ghost" onClick={() => setHealthExpanded(prev => !prev)}>{healthExpanded ? 'Collapse' : 'Expand'}</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginTop: '8px', fontSize: '0.8rem' }}>
            {(() => {
              const byTopic = new Map<string, RssHealthEntry[]>();
              for (const entry of rssHealth) {
                const key = entry.topic_name || `Topic ${entry.topic_id}`;
                if (!byTopic.has(key)) byTopic.set(key, []);
                byTopic.get(key)!.push(entry);
              }
              return Array.from(byTopic.entries()).map(([topicName, entries]) => {
                const okCount = entries.filter(e => e.status === 'ok').length;
                const errorCount = entries.filter(e => e.status === 'error').length;
                const emptyCount = entries.filter(e => e.status === 'empty').length;
                return (
                  <div key={topicName} style={{ background: 'var(--bg-main)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '10px' }}>
                    <div style={{ fontWeight: 600, marginBottom: '6px' }}>{topicName}</div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <span style={{ color: '#10b981' }}>{okCount} ok</span>
                      <span style={{ color: '#f59e0b' }}>{emptyCount} empty</span>
                      <span style={{ color: '#ef4444' }}>{errorCount} error</span>
                    </div>
                    {healthExpanded && entries.map(e => (
                      <div key={e.id} style={{ marginTop: '6px', padding: '4px 0', borderTop: '1px solid var(--border-color)' }}>
                        <div style={{ fontFamily: 'monospace', fontSize: '0.72rem', wordBreak: 'break-all' }}>{e.rss_url}</div>
                        <div style={{ display: 'flex', gap: '6px', marginTop: '2px' }}>
                          <span className={`health-badge health-${e.status}`}>{e.status}</span>
                          <span className="muted">{e.items_fetched} items</span>
                          {e.last_checked_at && <span className="muted">{new Date(e.last_checked_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })}</span>}
                        </div>
                        {e.last_error && <div style={{ color: '#ef4444', fontSize: '0.7rem', marginTop: '2px' }}>{e.last_error}</div>}
                      </div>
                    ))}
                  </div>
                );
              });
            })()}
          </div>
        </div>
      )}

      {showDeveloperPanels && systemStatus && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <h3>Runtime Diagnostics</h3>
          <p className="muted ui-font" style={{ margin: '0 0 10px' }}>
            Health snapshot of scheduler and backend capacity. Use this for debugging deployment/runtime issues.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.85rem' }}>
            <div><strong>Started:</strong> {systemStatus.started_at ? new Date(systemStatus.started_at).toLocaleString() : 'N/A'}</div>
            <div><strong>Scheduler:</strong> {systemStatus.scheduler_running ? 'Running' : 'Stopped'}</div>
            <div><strong>Active Research:</strong> {systemStatus.active_research} / {systemStatus.max_concurrent_research}</div>
            <div><strong>Rate Limit:</strong> {systemStatus.rate_limit_per_min} req/min</div>
          </div>
          {systemStatus.jobs.length > 0 && (
            <div style={{ marginTop: '0.75rem' }}>
              <strong>Scheduled Jobs ({systemStatus.jobs.length})</strong>
              <div className="topic-list" style={{ marginTop: '0.25rem' }}>
                {systemStatus.jobs.map(job => (
                  <div key={job.id} className="topic-card" style={{ borderLeftColor: '#6366f1', padding: '0.5rem 0.75rem' }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{job.id}</div>
                      <div className="muted" style={{ fontSize: '0.75rem' }}>Next: {job.next_run ? new Date(job.next_run).toLocaleString() : 'N/A'}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {showDeveloperPanels && topics.length > 0 && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3>Execution History</h3>
            <select
              className="settings-select"
              value={runStatsTopicId ? String(runStatsTopicId) : ''}
              onChange={(e) => setRunStatsTopicId(Number(e.target.value))}
            >
              {topics.map((topic) => (
                <option key={topic.id} value={String(topic.id)}>
                  {topic.name}
                </option>
              ))}
            </select>
          </div>
          <p className="muted ui-font" style={{ margin: '0 0 10px' }}>
            Recent collect/brief job outcomes per topic. Useful for monitoring ingestion quality and schedule health.
          </p>
          <div className="topic-list" style={{ marginTop: '8px' }}>
            {runStats.slice(0, 8).map((item) => (
              <div key={item.id} className="topic-card">
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>
                    {item.run_type} | {item.status}
                  </div>
                  <div className="muted">
                    {item.items_collected} collected | {item.items_saved} saved
                    {item.started_at ? ` | ${new Date(item.started_at).toLocaleString()}` : ''}
                  </div>
                </div>
              </div>
            ))}
            {runStats.length === 0 && <div className="muted">No run history for this topic yet.</div>}
          </div>
        </div>
      )}
      </div>
    </section>
  );
}
