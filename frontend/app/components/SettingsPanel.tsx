'use client';

import { useEffect, useState } from 'react';
import { apiFetch, Topic, SystemStatus, RssHealthEntry, AppConfig, StarterPack, getTopicColor, toCsv } from './api';
import { isReadOnlyDemo } from './demoMode';

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

/* 鈹€鈹€ Reusable list-of-inputs editor 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */

function ListEditor({
  items,
  onChange,
  placeholder,
  inputType = 'text',
  addLabel,
}: {
  items: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
  inputType?: string;
  addLabel: string;
}) {
  const update = (idx: number, value: string) => {
    const next = items.map((v, i) => (i === idx ? value : v));
    onChange(next);
  };
  const remove = (idx: number) => {
    onChange(items.filter((_, i) => i !== idx));
  };
  const add = () => onChange([...items, '']);

  return (
    <div className="list-editor">
      {items.map((item, idx) => (
        <div key={idx} className="list-editor-row">
          <input
            type={inputType}
            value={item}
            onChange={(e) => update(idx, e.target.value)}
            placeholder={placeholder}
          />
          <button
            type="button"
            className="list-editor-remove"
            onClick={() => remove(idx)}
            title="Remove"
          >
            &times;
          </button>
        </div>
      ))}
      <button type="button" className="list-editor-add" onClick={add}>
        + {addLabel}
      </button>
    </div>
  );
}

/* 鈹€鈹€ Main component 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */

export default function SettingsPanel({ topics, onTopicsChange }: Props) {
  const showDeveloperPanels = process.env.NEXT_PUBLIC_SHOW_DEV_PANELS === '1';
  const readOnlyDemo = isReadOnlyDemo();
  const allowAdminActions =
    !readOnlyDemo && process.env.NEXT_PUBLIC_ARCBRIEF_ENABLE_ADMIN_ACTIONS !== '0';

  // Create form state (arrays, not comma strings)
  const [topicName, setTopicName] = useState('');
  const [topicKeywords, setTopicKeywords] = useState<string[]>(['']);
  const [topicRss, setTopicRss] = useState<string[]>(['']);
  const [topicFrequency, setTopicFrequency] = useState(4);
  const [topicPushTime, setTopicPushTime] = useState('08:00');
  const [topicIsActive, setTopicIsActive] = useState(true);
  const [notice, setNotice] = useState('');

  // Edit state (arrays)
  const [editingTopic, setEditingTopic] = useState<Topic | null>(null);
  const [editName, setEditName] = useState('');
  const [editKeywords, setEditKeywords] = useState<string[]>([]);
  const [editRss, setEditRss] = useState<string[]>([]);
  const [editFrequency, setEditFrequency] = useState(4);
  const [editPushTime, setEditPushTime] = useState('08:00');
  const [editIsActive, setEditIsActive] = useState(true);

  // RSS source detail expand per topic
  const [expandedTopicSources, setExpandedTopicSources] = useState<number | null>(null);

  // System status
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);

  // RSS Health
  const [rssHealth, setRssHealth] = useState<RssHealthEntry[]>([]);
  const [healthExpanded, setHealthExpanded] = useState(false);
  const [appConfig, setAppConfig] = useState<AppConfig | null>(null);
  const [configLoaded, setConfigLoaded] = useState(false);
  const [starterPacks, setStarterPacks] = useState<StarterPack[]>([]);
  const [applyingPackId, setApplyingPackId] = useState<string | null>(null);
  const [configSaving, setConfigSaving] = useState(false);
  const [runStats, setRunStats] = useState<RunStat[]>([]);
  const [runStatsTopicId, setRunStatsTopicId] = useState<number | null>(null);
  const [regenRunning, setRegenRunning] = useState(false);

  const refreshSystemStatus = async () => {
    try {
      const res = await apiFetch('/system/status');
      if (!res.ok) return;
      const data = await res.json();
      setSystemStatus(data);
    } catch {}
  };

  useEffect(() => {
    setConfigLoaded(false);
    refreshSystemStatus();
    apiFetch('/starter-packs').then(r => r.ok ? r.json() : []).then(d => setStarterPacks(Array.isArray(d) ? d : [])).catch(() => setStarterPacks([]));
    apiFetch('/rss-health').then(r => r.ok ? r.json() : null).then(d => d && setRssHealth(d.sources || [])).catch(() => {});
    apiFetch('/config')
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setAppConfig(d))
      .catch(() => {})
      .finally(() => setConfigLoaded(true));
  }, [allowAdminActions, showDeveloperPanels]);

  useEffect(() => {
    if (!showDeveloperPanels || !allowAdminActions) return;
    if (topics.length === 0) {
      setRunStatsTopicId(null);
      return;
    }
    if (!runStatsTopicId || !topics.some((topic) => topic.id === runStatsTopicId)) {
      setRunStatsTopicId(topics[0].id);
    }
  }, [topics, runStatsTopicId, showDeveloperPanels, allowAdminActions]);

  useEffect(() => {
    if (!showDeveloperPanels || !allowAdminActions) return;
    if (!runStatsTopicId) return;
    apiFetch(`/topics/${runStatsTopicId}/run-stats`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setRunStats(Array.isArray(data) ? data : []))
      .catch(() => setRunStats([]));
  }, [runStatsTopicId, showDeveloperPanels, allowAdminActions]);

  const clean = (arr: string[]) => arr.map(s => s.trim()).filter(Boolean);
  const orderedTopics = [...topics].sort(
    (a, b) => Number(b.is_active) - Number(a.is_active) || a.name.localeCompare(b.name),
  );

  const createTopic = async () => {
    if (!allowAdminActions) {
      setNotice('Admin actions are disabled in public demo mode.');
      return;
    }
    if (!topicName.trim()) { setNotice('Please enter a topic name.'); return; }
    setNotice('');
    try {
      const res = await apiFetch('/topics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: topicName.trim(),
          keywords: clean(topicKeywords),
          rss_sources: clean(topicRss),
          scrape_frequency_hours: topicFrequency,
          push_time: topicPushTime,
          push_channels: ['discord'],
          is_active: topicIsActive,
        }),
      });
      if (!res.ok) { setNotice('Topic creation failed.'); return; }
      onTopicsChange();
      setNotice('Topic created successfully!');
      setTopicName('');
      setTopicKeywords(['']);
      setTopicRss(['']);
      setTopicIsActive(true);
    } catch { setNotice('Topic creation failed.'); }
  };

  const applyStarterPack = async (packId: string) => {
    if (!allowAdminActions) {
      setNotice('Admin actions are disabled in public demo mode.');
      return;
    }
    setApplyingPackId(packId);
    setNotice('');
    try {
      const res = await apiFetch('/starter-packs/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pack_id: packId }),
      });
      if (!res.ok) {
        setNotice('Starter pack apply failed.');
        setApplyingPackId(null);
        return;
      }
      const data = await res.json();
      const createdCount = Number(data?.created_count || 0);
      const existingCount = Array.isArray(data?.existing_topics) ? data.existing_topics.length : 0;
      setNotice(`Starter pack applied. Created ${createdCount} topics, skipped ${existingCount} existing topics.`);
      onTopicsChange();
    } catch {
      setNotice('Starter pack apply failed.');
    }
    setApplyingPackId(null);
  };

  const deleteTopic = async (topicId: number) => {
    if (!allowAdminActions) {
      setNotice('Admin actions are disabled in public demo mode.');
      return;
    }
    if (!confirm('Delete this topic?')) return;
    try {
      await apiFetch(`/topics/${topicId}`, { method: 'DELETE' });
      onTopicsChange();
    } catch {}
  };

  const startEdit = (topic: Topic) => {
    setEditingTopic(topic);
    setEditName(topic.name);
    setEditKeywords(topic.keywords.length > 0 ? [...topic.keywords] : ['']);
    setEditRss(topic.rss_sources.length > 0 ? [...topic.rss_sources] : ['']);
    setEditFrequency(topic.scrape_frequency_hours);
    setEditPushTime(topic.push_time);
    setEditIsActive(topic.is_active);
  };

  const saveEdit = async () => {
    if (!allowAdminActions) {
      setNotice('Admin actions are disabled in public demo mode.');
      return;
    }
    if (!editingTopic) return;
    const payload: Record<string, unknown> = {};
    if (editName.trim() !== editingTopic.name) payload.name = editName.trim();
    const newKw = clean(editKeywords);
    if (JSON.stringify(newKw) !== JSON.stringify(editingTopic.keywords)) payload.keywords = newKw;
    const newRss = clean(editRss);
    if (JSON.stringify(newRss) !== JSON.stringify(editingTopic.rss_sources)) payload.rss_sources = newRss;
    if (editFrequency !== editingTopic.scrape_frequency_hours) payload.scrape_frequency_hours = editFrequency;
    if (editPushTime !== editingTopic.push_time) payload.push_time = editPushTime;
    if (editIsActive !== editingTopic.is_active) payload.is_active = editIsActive;
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

  const toggleTopicActive = async (topic: Topic) => {
    if (!allowAdminActions) {
      setNotice('Admin actions are disabled in public demo mode.');
      return;
    }
    setNotice('');
    try {
      const res = await apiFetch(`/topics/${topic.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !topic.is_active }),
      });
      if (!res.ok) {
        setNotice('Status update failed.');
        return;
      }
      setNotice(`${topic.name} ${topic.is_active ? 'paused' : 'enabled'}.`);
      onTopicsChange();
    } catch {
      setNotice('Status update failed.');
    }
  };

  const saveConfig = async () => {
    if (!allowAdminActions) {
      setNotice('Admin actions are disabled in public demo mode.');
      return;
    }
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
      await refreshSystemStatus();
      setNotice('Configuration saved.');
    } catch {
      setNotice('Configuration update failed.');
    }
    setConfigSaving(false);
  };

  const regenerateTodayBriefs = async () => {
    if (!allowAdminActions) {
      setNotice('Admin actions are disabled in public demo mode.');
      return;
    }
    setRegenRunning(true);
    setNotice('');
    try {
      const language = appConfig?.report_language;
      const body = language ? JSON.stringify({ language }) : undefined;
      const res = await apiFetch('/topics/brief_all', {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body,
      });
      if (!res.ok) {
        setNotice('Failed to regenerate today briefs.');
        setRegenRunning(false);
        return;
      }
      setNotice('Today briefs regenerated. Language setting applies to newly generated briefs.');
    } catch {
      setNotice('Failed to regenerate today briefs.');
    }
    setRegenRunning(false);
  };

  return (
    <section className="panel settings-panel">
      <div className="module-head">
        <h2>Agent Protocol</h2>
        <p className="ui-font">System configuration and collection directives.</p>
      </div>
      {!allowAdminActions && (
        <div className="card" style={{ marginBottom: '12px' }}>
          <div className="muted">
            {readOnlyDemo
              ? 'This is a read-only demo. Topic intake, brief generation, and configuration changes are disabled; the values below are shown for reference.'
              : (
                <>
                  Write operations are disabled (public demo mode). To enable locally: set <code>NEXT_PUBLIC_ARCBRIEF_ENABLE_ADMIN_ACTIONS=1</code> in <code>frontend/.env.local</code>, or remove the variable entirely. For production, update the value in Vercel Environment Variables.
                </>
              )}
          </div>
        </div>
      )}

      <div className="settings-section">
        <h3 className="settings-section-title">Intelligence Scope</h3>
        <div className="grid-two settings-grid-scope">
          {/* 鈹€鈹€ Left: Focus Topics 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */}
          <div className="card settings-scope-focus">
            <h3>Focus Topics</h3>
            <div className="topic-list settings-topic-list">
              {orderedTopics.map((topic, idx) => {
                const color = getTopicColor(idx);
                const isEditing = editingTopic?.id === topic.id;
                const isSourcesExpanded = expandedTopicSources === topic.id;
                return (
                  <div key={topic.id} className={`topic-card ${topic.is_active ? '' : 'topic-card-inactive'}`} style={{ borderLeftColor: color.border }}>
                    {isEditing ? (
                      /* 鈹€鈹€ Edit mode 鈹€鈹€ */
                      <div className="form topic-edit-form" style={{ flex: 1, gap: '10px' }}>
                        <label>
                          Name
                          <input value={editName} onChange={e => setEditName(e.target.value)} placeholder="Topic name" />
                        </label>

                        <label>
                          Keyword Groups
                          <span className="label-hint">Use | for OR within a group, e.g. &quot;OpenAI | Anthropic | DeepMind&quot;</span>
                        </label>
                        <ListEditor
                          items={editKeywords}
                          onChange={setEditKeywords}
                          placeholder="e.g. OpenAI | Anthropic | DeepMind"
                          addLabel="Add Group"
                        />

                        <label>
                          RSS Sources
                          <span className="label-hint">One URL per row</span>
                        </label>
                        <ListEditor
                          items={editRss}
                          onChange={setEditRss}
                          placeholder="https://example.com/feed/rss.xml"
                          inputType="url"
                          addLabel="Add Source"
                        />

                        <div className="inline">
                          <label>Frequency (h)<input type="number" min={1} value={editFrequency} onChange={e => setEditFrequency(Number(e.target.value))} /></label>
                          <label>Push time<input type="time" value={editPushTime} onChange={e => setEditPushTime(e.target.value)} /></label>
                        </div>
                        <label className="settings-inline-check">
                          <input type="checkbox" checked={editIsActive} onChange={(e) => setEditIsActive(e.target.checked)} />
                          <span>Enabled in Focus Topics and scheduled refresh</span>
                        </label>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <button className="paper-primary-btn" onClick={saveEdit}>Save</button>
                          <button className="ghost" onClick={() => setEditingTopic(null)}>Cancel</button>
                        </div>
                      </div>
                    ) : (
                      /* 鈹€鈹€ View mode 鈹€鈹€ */
                      <>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className="topic-name">{topic.name}</div>
                          <div style={{ marginBottom: '6px' }}>
                            <span className={`settings-badge ${topic.is_active ? 'status-on' : 'status-off'}`}>
                              {topic.is_active ? 'Enabled' : 'Paused'}
                            </span>
                          </div>
                          <div className="keyword-tags">
                            {topic.keywords.length > 0
                              ? topic.keywords.map((kw, ki) => (
                                  <span key={ki} className="keyword-tag">{kw}</span>
                                ))
                              : <span className="muted">No keywords</span>
                            }
                          </div>
                          <div className="muted" style={{ marginTop: '4px' }}>
                            <span
                              className="source-count-toggle"
                              onClick={() => setExpandedTopicSources(isSourcesExpanded ? null : topic.id)}
                            >
                              {topic.rss_sources.length} RSS sources {isSourcesExpanded ? '▲' : '▼'}
                            </span>
                            {' | '} every {topic.scrape_frequency_hours}h {' | '} push {topic.push_time}
                          </div>
                          {isSourcesExpanded && topic.rss_sources.length > 0 && (
                            <div className="source-url-list">
                              {topic.rss_sources.map((url, si) => (
                                <div key={si} className="source-url-item">{url}</div>
                              ))}
                            </div>
                          )}
                        </div>
                        {allowAdminActions && (
                          <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                            <button
                              className="delete-btn"
                              onClick={() => toggleTopicActive(topic)}
                              title={topic.is_active ? 'Pause this topic' : 'Enable this topic'}
                            >
                              {topic.is_active ? 'II' : '▶'}
                            </button>
                            <button className="delete-btn" style={{ borderColor: color.border, color: color.text }} onClick={() => startEdit(topic)}>&#9998;</button>
                            <button className="delete-btn" onClick={() => deleteTopic(topic.id)}>&times;</button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
              {orderedTopics.length === 0 && <div className="muted" style={{ padding: '1rem', textAlign: 'center' }}>No topics yet. Use the form to create your first topic.</div>}
            </div>
          </div>

          {/* 鈹€鈹€ Right: Topic Intake 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */}
          <div className="card settings-scope-intake">
            <h3>Topic Intake</h3>
            {starterPacks.length > 0 && (
              <div style={{ marginBottom: '14px' }}>
                <div className="muted" style={{ marginBottom: '8px' }}>
                  Starter Packs
                </div>
                <div style={{ display: 'grid', gap: '10px' }}>
                  {starterPacks.map((pack) => (
                    <div key={pack.id} style={{ border: '1px solid var(--border-color)', borderRadius: '10px', padding: '10px', background: 'var(--bg-main)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ fontWeight: 600 }}>{pack.name}</div>
                          <div className="muted" style={{ marginTop: '2px' }}>{pack.ideal_for}</div>
                        </div>
                        <span className="settings-badge status-on">{pack.signal_density}</span>
                      </div>
                      <div className="muted" style={{ marginTop: '8px' }}>{pack.focus}</div>
                      <div className="muted" style={{ marginTop: '6px', fontSize: '0.82rem' }}>
                        Expected: {pack.content_types.join(' · ')} | Recommended language: {pack.recommended_language}
                      </div>
                      <div style={{ marginTop: '8px', display: 'grid', gap: '4px', fontSize: '0.82rem' }}>
                        {pack.topics.map((topic) => (
                          <div key={topic.name}>{topic.name} · {topic.rss_count} RSS · {topic.keyword_groups} keyword groups</div>
                        ))}
                      </div>
                      {allowAdminActions && (
                        <button
                          className="paper-primary-btn"
                          style={{ marginTop: '10px' }}
                          onClick={() => applyStarterPack(pack.id)}
                          disabled={applyingPackId === pack.id}
                        >
                          {applyingPackId === pack.id ? 'Applying...' : 'Apply Pack'}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {!allowAdminActions ? (
              <div className="muted">
                {readOnlyDemo
                  ? 'Topic intake is disabled in this read-only demo.'
                  : 'Topic intake is disabled in public demo mode.'}
              </div>
            ) : (
            <div className="form">
              <label>Name *<input value={topicName} onChange={e => setTopicName(e.target.value)} placeholder="e.g., AI Daily" /></label>

              <label>
                Keyword Groups
                <span className="label-hint">Use | for OR within a group</span>
              </label>
              <ListEditor
                items={topicKeywords}
                onChange={setTopicKeywords}
                placeholder="e.g. GPT | Claude | Gemini"
                addLabel="Add Group"
              />

              <label>
                RSS Sources
                <span className="label-hint">One URL per row</span>
              </label>
              <ListEditor
                items={topicRss}
                onChange={setTopicRss}
                placeholder="https://example.com/feed/rss.xml"
                inputType="url"
                addLabel="Add Source"
              />

              <div className="inline">
                <label>Frequency (hours)<input type="number" min={1} value={topicFrequency} onChange={e => setTopicFrequency(Number(e.target.value))} /></label>
                <label>Push time<input type="time" value={topicPushTime} onChange={e => setTopicPushTime(e.target.value)} /></label>
              </div>
              <label className="settings-inline-check">
                <input type="checkbox" checked={topicIsActive} onChange={(e) => setTopicIsActive(e.target.checked)} />
                <span>Enable immediately after create</span>
              </label>
              <button className="paper-primary-btn" onClick={createTopic}>Create Topic</button>
              {notice && <div className="notice">{notice}</div>}
            </div>
            )}
          </div>
        </div>
      </div>

      <div className="settings-section">
        <h3 className="settings-section-title">Agent Behavior</h3>
        <div className="card">
          {!appConfig && (
            <div className="muted">
              {configLoaded ? 'Configuration is unavailable in this mode.' : 'Loading protocol configuration...'}
            </div>
          )}
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
                  disabled={!allowAdminActions}
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
                  disabled={!allowAdminActions}
                  onChange={(e) => setAppConfig({ ...appConfig, critical_analysis_layer: e.target.checked })}
                />
              </div>
              <label style={{ marginTop: '14px' }}>
                Priority Watchlist (Entities)
                <textarea
                  rows={3}
                  value={appConfig.entity_watchlist || ''}
                  placeholder="e.g. Sam Altman, TSMC 3nm, GPT-5"
                  disabled={!allowAdminActions}
                  onChange={(e) => setAppConfig({ ...appConfig, entity_watchlist: e.target.value })}
                />
              </label>
              <label style={{ marginTop: '14px' }}>
                Cognitive Model
                <select
                  value={appConfig.cognitive_model || 'Neutral (Fact-first)'}
                  disabled={!allowAdminActions}
                  onChange={(e) => setAppConfig({ ...appConfig, cognitive_model: e.target.value })}
                >
                  <option>Neutral (Fact-first)</option>
                  <option>Critique-heavy (Skeptic)</option>
                </select>
              </label>
              {allowAdminActions && (
                <button className="paper-primary-btn" onClick={saveConfig} disabled={configSaving} style={{ marginTop: '14px' }}>
                  {configSaving ? 'Saving...' : 'Save Behavior & Watchlist'}
                </button>
              )}
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
              Report Output Language
              <select
                value={appConfig.report_language}
                disabled={!allowAdminActions}
                onChange={(e) => setAppConfig({ ...appConfig, report_language: e.target.value })}
              >
                <option>English (US)</option>
                <option>Chinese (Simplified)</option>
                <option>Japanese</option>
              </select>
              <span className="muted" style={{ fontSize: '0.78em', display: 'block', marginTop: '4px' }}>
                Affects all AI output: briefs, research reports, and chat replies.
              </span>
            </label>
            <label>
              Primary LLM Model
              <select
                value={appConfig.primary_model}
                disabled={!allowAdminActions}
                onChange={(e) => setAppConfig({ ...appConfig, primary_model: e.target.value })}
              >
                <option>Qwen3 MAX</option>
                <option>GPT-4o mini (OpenAI)</option>
                <option>GPT-4o (OpenAI)</option>
                <option>GPT-4.1 mini (OpenAI)</option>
                <option>Claude 3.5 Sonnet (Anthropic)</option>
                <option>Gemini 1.5 Pro (Google)</option>
              </select>
              <span className="muted" style={{ fontSize: '0.78em', display: 'block', marginTop: '4px' }}>
                Backend model for all AI tasks. Requires matching API key.
              </span>
            </label>
          </div>
          <div className="inline" style={{ marginTop: '14px' }}>
            <label>
              Search Provider
              <select
                value={appConfig.search_provider}
                disabled={!allowAdminActions}
                onChange={(e) => setAppConfig({ ...appConfig, search_provider: e.target.value })}
              >
                <option>Tavily Search API</option>
                <option>Bocha Search</option>
                <option>Zhipu Web Search</option>
                <option>Volcano Engine</option>
                <option>Exa Search</option>
              </select>
              <span className="muted" style={{ fontSize: '0.78em', display: 'block', marginTop: '4px' }}>
                Provider for research-stage web retrieval. Strict mode fails the run when provider is unavailable.
              </span>
            </label>
            <label>
              API Key Status
              <input value="Managed by environment variables" disabled />
              <span className="muted" style={{ fontSize: '0.78em', display: 'block', marginTop: '4px' }}>
                Configure provider keys in backend environment variables.
              </span>
            </label>
          </div>
          <div className="muted" style={{ marginTop: '10px' }}>
            Language setting only affects newly generated briefs. Existing briefs keep their original language.
          </div>
          {allowAdminActions && (
            <button className="ghost" onClick={regenerateTodayBriefs} disabled={regenRunning} style={{ marginTop: '8px' }}>
              {regenRunning ? 'Regenerating...' : 'Regenerate Today Briefs'}
            </button>
          )}
          {systemStatus && (
            <div style={{ marginTop: '14px', borderTop: '1px solid var(--border-color)', paddingTop: '10px' }}>
              <h4 style={{ margin: '0 0 6px 0' }}>Search Diagnostics</h4>
              <div className="muted" style={{ fontSize: '0.86em', lineHeight: 1.6 }}>
                <div>Configured provider: <strong>{appConfig?.search_provider || systemStatus.search_provider_configured || 'N/A'}</strong></div>
                <div>Effective provider: <strong>{systemStatus.search_provider_effective || 'N/A'}</strong></div>
                <div>Unavailable reason: {systemStatus.search_provider_fallback || 'None'}</div>
                <div>LLM-assisted search: {systemStatus.search_llm_assisted ? 'Yes' : 'No'}</div>
              </div>
              <div className="muted" style={{ fontSize: '0.78em', marginTop: '6px' }}>
                Diagnostics are computed from current configuration and environment in real time.
              </div>
            </div>
          )}
          {allowAdminActions && (
            <button className="paper-primary-btn" onClick={saveConfig} disabled={configSaving} style={{ marginTop: '14px' }}>
              {configSaving ? 'Saving...' : 'Save Configuration'}
            </button>
          )}
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

      {allowAdminActions && showDeveloperPanels && systemStatus && (
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

      {allowAdminActions && showDeveloperPanels && orderedTopics.length > 0 && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3>Execution History</h3>
            <select
              className="settings-select"
              value={runStatsTopicId ? String(runStatsTopicId) : ''}
              onChange={(e) => setRunStatsTopicId(Number(e.target.value))}
            >
              {orderedTopics.map((topic) => (
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
