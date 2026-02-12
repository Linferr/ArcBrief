'use client';

import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch, Topic } from './components/api';
import NewsFeedPanel from './components/NewsFeedPanel';
import ResearchPanel from './components/ResearchPanel';
import SettingsPanel from './components/SettingsPanel';
import ArchivesPanel from './components/ArchivesPanel';

type PanelKey = 'news' | 'research' | 'settings' | 'archives';
type ThemeMode = 'warm' | 'cool';

const THEME_KEY = 'arcbrief-theme';

export default function Page() {
  const [panel, setPanel] = useState<PanelKey>('news');
  const [topics, setTopics] = useState<Topic[]>([]);
  const [researchRunning, setResearchRunning] = useState(false);
  const [pendingResearchQuery, setPendingResearchQuery] = useState<string | undefined>();
  const [theme, setTheme] = useState<ThemeMode>('warm');

  const loadTopics = async () => {
    try {
      const res = await apiFetch('/topics');
      if (res.ok) setTopics(await res.json());
    } catch {}
  };

  useEffect(() => {
    loadTopics();
  }, []);

  const handleSendToResearch = useCallback((query: string) => {
    setPendingResearchQuery(query);
    setPanel('research');
  }, []);

  const handlePendingQueryConsumed = useCallback(() => {
    setPendingResearchQuery(undefined);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const savedTheme = window.localStorage.getItem(THEME_KEY);
    if (savedTheme === 'cool') setTheme('cool');
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const body = document.body;
    if (theme === 'cool') body.setAttribute('data-theme', 'cool');
    else body.removeAttribute('data-theme');
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const navItems: { key: PanelKey; label: string; icon: ReactNode }[] = useMemo(
    () => [
      {
        key: 'news',
        label: 'Daily Brief',
        icon: (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
            <path d="M5 5h10a2 2 0 0 1 2 2v12H7a2 2 0 0 0-2 2V5z" />
            <path d="M7 7h8M7 11h8M7 15h6" />
          </svg>
        ),
      },
      {
        key: 'research',
        label: 'Deep Research',
        icon: (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.5-3.5" />
          </svg>
        ),
      },
      {
        key: 'settings',
        label: 'Settings',
        icon: (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
            <path d="M12 8.5A3.5 3.5 0 1 1 8.5 12 3.5 3.5 0 0 1 12 8.5Z" />
            <path d="M19.4 15a1 1 0 0 0 .2 1.1l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9V20a2 2 0 0 1-4 0v-.2a1 1 0 0 0-.6-.9 1 1 0 0 0-1.1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6H4a2 2 0 0 1 0-4h.2a1 1 0 0 0 .9-.6 1 1 0 0 0-.2-1.1l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1 1 0 0 0 1.1.2h.2a1 1 0 0 0 .6-.9V4a2 2 0 0 1 4 0v.2a1 1 0 0 0 .6.9h.2a1 1 0 0 0 1.1-.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1 1 0 0 0-.2 1.1v.2a1 1 0 0 0 .9.6H20a2 2 0 0 1 0 4h-.2a1 1 0 0 0-.9.6z" />
          </svg>
        ),
      },
    ],
    []
  );

  const panelMeta: Record<PanelKey, { title: string; breadcrumb: string }> = {
    news: { title: 'Daily Brief', breadcrumb: 'Daily Brief' },
    research: { title: 'Deep Research', breadcrumb: 'Deep Research' },
    settings: { title: 'Agent Protocol', breadcrumb: 'System Config' },
    archives: { title: 'Archive Library', breadcrumb: 'Archives' },
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-title">
            <span className="brand-bar" />
            ArcBrief
          </div>
          <p className="brand-subtitle">Intelligence Desk</p>
        </div>

        <nav className="side-nav">
          {navItems.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${panel === item.key ? 'active' : ''} ${
                item.key === 'research' && researchRunning ? 'running' : ''
              }`}
              onClick={() => setPanel(item.key)}
            >
              <span className="nav-icon" aria-hidden>
                {item.icon}
              </span>
              <span>{item.label}</span>
            </button>
          ))}

          <div className="library-group">
            <div className="library-title">Library</div>
            <button className={`nav-item ${panel === 'archives' ? 'active' : ''}`} onClick={() => setPanel('archives')}>
              <span className="nav-icon" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                  <path d="M4 6h8a2 2 0 0 1 2 2v10H6a2 2 0 0 0-2 2V6z" />
                  <path d="M14 9h6v11H14z" />
                </svg>
              </span>
              <span>Archives</span>
            </button>
          </div>
        </nav>

        <div className="sidebar-foot">
          <button className="system-pill">
            <span className="system-dot" />
            <span>System Operational</span>
          </button>
        </div>
      </aside>

      <main className="workspace">
        <header className="workspace-topbar">
          <div className="workspace-crumb ui-font">
            <span>Workspace</span>
            <span className="slash">/</span>
            <span className="current">{panelMeta[panel].breadcrumb}</span>
          </div>
          <div className="workspace-status ui-font">
            <span className="version-tag">v2.4.0</span>
            <div className="avatar-chip">OP</div>
          </div>
        </header>

        <div className="content-scroll" id="content-container">
          <div style={{ display: panel === 'news' ? 'block' : 'none' }}>
            <NewsFeedPanel
              topics={topics}
              onNavigateSettings={() => setPanel('settings')}
              onNavigateArchive={() => setPanel('archives')}
              onSendToResearch={handleSendToResearch}
            />
          </div>
          <div style={{ display: panel === 'research' ? 'block' : 'none' }}>
            <ResearchPanel
              onRunningChange={setResearchRunning}
              pendingQuery={pendingResearchQuery}
              onPendingQueryConsumed={handlePendingQueryConsumed}
            />
          </div>
          <div style={{ display: panel === 'settings' ? 'block' : 'none' }}>
            <SettingsPanel topics={topics} onTopicsChange={loadTopics} />
          </div>
          <div style={{ display: panel === 'archives' ? 'block' : 'none' }}>
            <ArchivesPanel topics={topics} />
          </div>
        </div>
      </main>

      <button
        className="floating-theme-btn"
        onClick={() => setTheme((prev) => (prev === 'warm' ? 'cool' : 'warm'))}
        aria-label={theme === 'warm' ? 'Switch to cool mode' : 'Switch to paper mode'}
        title={theme === 'warm' ? 'Switch to cool mode' : 'Switch to paper mode'}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          {theme === 'warm' ? (
            <path d="M20.354 15.354A9 9 0 0 1 8.646 3.646 9.003 9.003 0 0 0 12 21a9.003 9.003 0 0 0 8.354-5.646z" />
          ) : (
            <path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364-.707-.707M6.343 6.343l-.707-.707m12.728 0-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0z" />
          )}
        </svg>
      </button>
    </div>
  );
}
