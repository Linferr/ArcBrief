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
          <svg viewBox="0 0 24 24" className="icon-line" aria-hidden>
            <path d="M4 22h16a2 2 0 002-2V4a2 2 0 00-2-2H8a2 2 0 00-2 2v16a2 2 0 01-2 2z" />
            <path d="M14 9l-2 2 2 2m-2-2h6" />
            <path d="M9 12h.01" strokeWidth="2.5" />
          </svg>
        ),
      },
      {
        key: 'research',
        label: 'Deep Research',
        icon: (
          <svg viewBox="0 0 24 24" className="icon-line" aria-hidden>
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
            <path d="M11 7v4m-2-2h4" opacity="0.7" />
          </svg>
        ),
      },
      {
        key: 'settings',
        label: 'Settings',
        icon: (
          <svg viewBox="0 0 24 24" className="icon-line" aria-hidden>
            <line x1="4" y1="21" x2="4" y2="14" />
            <line x1="4" y1="10" x2="4" y2="3" />
            <line x1="12" y1="21" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12" y2="3" />
            <line x1="20" y1="21" x2="20" y2="16" />
            <line x1="20" y1="12" x2="20" y2="3" />
            <line x1="1" y1="14" x2="7" y2="14" />
            <line x1="9" y1="8" x2="15" y2="8" />
            <line x1="17" y1="16" x2="23" y2="16" />
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
        <div className="brand" style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '0 24px', marginBottom: '28px' }}>
          <svg className="icon-line icon-brand" style={{ width: '32px', height: '32px', color: 'var(--text-primary)', flexShrink: 0 }} viewBox="0 0 24 24" aria-hidden>
            <path d="M12 2L2 22h20L12 2z" />
            <path d="M6.5 13.5c2.5-3 7.5-3 11 0" /> 
          </svg>
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <div className="brand-title" style={{ fontSize: '21px', fontWeight: 700, letterSpacing: '0.02em', lineHeight: 1.1, padding: 0, margin: 0, display: 'block' }}>ArcBrief</div>
            <div className="brand-subtitle" style={{ fontSize: '10px', letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-tertiary)', fontWeight: 600, paddingLeft: 0, margin: '2px 0 0 0' }}>Intelligence Desk</div>
          </div>
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
                <svg viewBox="0 0 24 24" className="icon-line">
                  <polyline points="21 8 21 21 3 21 3 8" />
                  <rect x="1" y="3" width="22" height="5" />
                  <line x1="10" y1="12" x2="14" y2="12" />
                  <path d="M16.5 16.5c1-1 1-2.5 1-2.5s-.5-2-2-2.5" opacity="0.6"/>
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
              isVisible={panel === 'research'}
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
        style={{ border: '2px solid var(--bg-main)' }}
        onClick={() => setTheme((prev) => (prev === 'warm' ? 'cool' : 'warm'))}
        aria-label={theme === 'warm' ? 'Switch to cool mode' : 'Switch to paper mode'}
        title={theme === 'warm' ? 'Switch to cool mode' : 'Switch to paper mode'}
      >
        <svg viewBox="0 0 24 24" className="icon-line" style={{ width: '20px', height: '20px' }} aria-hidden>
          {theme === 'warm' ? (
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          ) : (
            <>
              <circle cx="12" cy="12" r="5"/>
              <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
            </>
          )}
        </svg>
      </button>
    </div>
  );
}