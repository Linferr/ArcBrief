'use client';

import { useEffect, useMemo, useState } from 'react';
import { apiFetch, downloadPdfResponse, readErrorMessage, RunEvent, RunSummary } from './api';
import MarkdownViewer from './MarkdownViewer';

const RECENT_COLLAPSED_COUNT = 3;
const ITERATIVE_LOG_LIMIT = 6;
const DISPLAY_ROUNDS = 3;

type UILanguage = 'English (US)' | 'Chinese (Simplified)' | 'Japanese';

type IterativeLabels = {
  search: string;
  summary: string;
  host: string;
  reflection: string;
};

type PipelineText = {
  pipelineTitle: string;
  decompositionTitle: string;
  decompositionPending: string;
  decompositionDone: (segments: number) => string;
  iterativeTitle: string;
  synthesisTitle: string;
  synthesisRunning: string;
  synthesisDone: string;
  completed: string;
  roundLabel: string;
  reportPreview: string;
  recentRuns: string;
  expand: string;
  collapse: string;
  loadMore: string;
  noHistory: string;
  iterativeStageLabels: IterativeLabels;
};

const PIPELINE_COPY: Record<UILanguage, PipelineText> = {
  'English (US)': {
    pipelineTitle: 'Pipeline Progress',
    decompositionTitle: 'Query Decomposition',
    decompositionPending: 'Awaiting run start.',
    decompositionDone: (segments: number) => `Mapped into ${segments} analysis segments.`,
    iterativeTitle: 'Iterative Research',
    synthesisTitle: 'Synthesis & Reporting',
    synthesisRunning: 'Composing final narrative and citations.',
    synthesisDone: 'Final report generated.',
    completed: 'Completed',
    roundLabel: 'Round',
    reportPreview: 'Report Preview',
    recentRuns: 'Recent Runs',
    expand: 'Expand',
    collapse: 'Collapse',
    loadMore: 'Load More',
    noHistory: 'No research history yet.',
    iterativeStageLabels: {
      search: 'Search',
      summary: 'Summary',
      host: 'Host Critique',
      reflection: 'Reflection',
    },
  },
  'Chinese (Simplified)': {
    pipelineTitle: 'Pipeline Progress',
    decompositionTitle: 'Query Decomposition',
    decompositionPending: 'Awaiting run start.',
    decompositionDone: (segments: number) => `Mapped into ${segments} analysis segments.`,
    iterativeTitle: 'Iterative Research',
    synthesisTitle: 'Synthesis & Reporting',
    synthesisRunning: 'Composing final narrative and citations.',
    synthesisDone: 'Final report generated.',
    completed: 'Completed',
    roundLabel: 'Round',
    reportPreview: 'Report Preview',
    recentRuns: 'Recent Runs',
    expand: 'Expand',
    collapse: 'Collapse',
    loadMore: 'Load More',
    noHistory: 'No research history yet.',
    iterativeStageLabels: {
      search: 'Search',
      summary: 'Summary',
      host: 'Host Critique',
      reflection: 'Reflection',
    },
  },
  Japanese: {
    pipelineTitle: 'Pipeline Progress',
    decompositionTitle: 'Query Decomposition',
    decompositionPending: 'Awaiting run start.',
    decompositionDone: (segments: number) => `Mapped into ${segments} analysis segments.`,
    iterativeTitle: 'Iterative Research',
    synthesisTitle: 'Synthesis & Reporting',
    synthesisRunning: 'Composing final narrative and citations.',
    synthesisDone: 'Final report generated.',
    completed: 'Completed',
    roundLabel: 'Round',
    reportPreview: 'Report Preview',
    recentRuns: 'Recent Runs',
    expand: 'Expand',
    collapse: 'Collapse',
    loadMore: 'Load More',
    noHistory: 'No research history yet.',
    iterativeStageLabels: {
      search: 'Search',
      summary: 'Summary',
      host: 'Host Critique',
      reflection: 'Reflection',
    },
  },
};

const formatRunTimestamp = (run: RunSummary): string => {
  const ts = run.created_at || run.started_at || run.finished_at;
  if (!ts) return 'N/A';
  return new Date(ts).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
};

interface Props {
  onRunningChange?: (running: boolean) => void;
  pendingQuery?: string;
  pendingBriefId?: number | null;
  onPendingQueryConsumed?: () => void;
  isVisible?: boolean;
}

export default function ResearchPanel({
  onRunningChange,
  pendingQuery,
  pendingBriefId,
  onPendingQueryConsumed,
  isVisible,
}: Props) {
  const [query, setQuery] = useState('');
  const [briefAnchorId, setBriefAnchorId] = useState<number | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState('idle');
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [report, setReport] = useState('');
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [recentExpanded, setRecentExpanded] = useState(false);
  const [selectedRun, setSelectedRun] = useState<RunSummary | null>(null);
  const [fullReport, setFullReport] = useState('');
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const [previewRunId, setPreviewRunId] = useState<string | null>(null);
  const [previewTitle, setPreviewTitle] = useState('');
  const [previewReport, setPreviewReport] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [runLanguage, setRunLanguage] = useState<UILanguage>('English (US)');

  useEffect(() => {
    onRunningChange?.(status === 'running');
  }, [status, onRunningChange]);

  useEffect(() => {
    if (pendingQuery) {
      setQuery(pendingQuery);
      setBriefAnchorId(pendingBriefId ?? null);
      onPendingQueryConsumed?.();
    }
  }, [pendingBriefId, pendingQuery, onPendingQueryConsumed]);

  const loadHistory = async (page = 1, append = false) => {
    try {
      const params = new URLSearchParams();
      params.set('page', String(page));
      params.set('size', '10');
      const res = await apiFetch(`/history?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      const results: RunSummary[] = data.results || [];
      setHistory((prev) => {
        if (!append) return results;
        const merged = [...prev];
        for (const item of results) {
          if (!merged.find((entry) => entry.run_id === item.run_id)) merged.push(item);
        }
        return merged;
      });
      setHistoryTotal(data.total || 0);
      setHistoryPage(data.page || 1);
    } catch {}
  };

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    if (isVisible === false) return;
    apiFetch('/config')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        const lang = d?.report_language;
        if (lang === 'Chinese (Simplified)' || lang === 'Japanese' || lang === 'English (US)') {
          setRunLanguage(lang);
        }
      })
      .catch(() => {});
  }, [isVisible]);

  useEffect(() => {
    if (!runId) return;
    let pollCount = 0;
    const MAX_POLLS = 650;
    const timer = setInterval(async () => {
      pollCount++;
      if (pollCount > MAX_POLLS) {
        clearInterval(timer);
        setStatus('timeout');
        setNotice('Research timeout after 15 minutes. The task may still be running on the server.');
        return;
      }
      try {
        const res = await apiFetch(`/status/${runId}`);
        if (!res.ok) return;
        const data = await res.json();
        setStatus(data.status);
        setEvents(data.events || []);
        if (data.report_content) setReport(data.report_content);
        if (data.status === 'done' || data.status === 'failed') {
          clearInterval(timer);
          loadHistory();
          if (data.status === 'failed') setNotice('Research failed. Check the report for details.');
        }
      } catch {}
    }, 1400);
    return () => clearInterval(timer);
  }, [runId]);

  const startRun = async () => {
    const cleanQuery = query.trim();
    if (!cleanQuery) {
      setNotice('Please enter a research question first.');
      return;
    }
    setStatus('running');
    setReport('');
    setEvents([]);
    setNotice('');
    try {
      const res = await apiFetch('/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: cleanQuery,
          language: runLanguage,
          brief_id: briefAnchorId ?? undefined,
        }),
      });
      const data = await res.json();
      if (data.run_id) setRunId(data.run_id);
      else {
        setStatus('idle');
        setNotice(data.message || 'Failed to start research.');
      }
    } catch {
      setStatus('idle');
      setNotice('Failed to start research.');
    }
  };

  const openReport = async (run: RunSummary) => {
    setSelectedRun(run);
    setIsReportOpen(true);
    setReportLoading(true);
    setFullReport('');
    try {
      const res = await apiFetch(`/report/${run.run_id}`);
      if (res.ok) setFullReport(await res.text());
      else setFullReport(await readErrorMessage(res, 'Report not found.'));
    } catch {
      setFullReport('Report load failed.');
    }
    setReportLoading(false);
  };

  const previewFromHistory = async (run: RunSummary) => {
    setPreviewRunId(run.run_id);
    setPreviewTitle(run.query);
    setPreviewLoading(true);
    setPreviewReport('');
    try {
      const res = await apiFetch(`/report/${run.run_id}`);
      if (res.ok) setPreviewReport(await res.text());
      else setPreviewReport(await readErrorMessage(res, 'Report not found.'));
    } catch {
      setPreviewReport('Report load failed.');
    }
    setPreviewLoading(false);
  };

  const clearPreview = () => {
    setPreviewRunId(null);
    setPreviewTitle('');
    setPreviewReport('');
    setPreviewLoading(false);
  };

  const closeReport = () => {
    setIsReportOpen(false);
    setSelectedRun(null);
    setFullReport('');
  };

  const downloadReportPdf = async (targetRunId: string) => {
    try {
      const res = await apiFetch(`/report/${targetRunId}/export/pdf`);
      const error = await downloadPdfResponse(res, `${targetRunId}.pdf`);
      if (error) setNotice(error);
    } catch {
      setNotice('PDF export failed.');
    }
  };

  const semanticStages = ['outline', 'search', 'summary', 'host', 'reflection', 'final', 'error'];
  const lastSemanticEvent = useMemo(
    () => [...events].reverse().find((e) => semanticStages.includes(e.stage)),
    [events]
  );
  const stageNow =
    status === 'done' || status === 'failed' || status === 'timeout'
      ? 'final'
      : (lastSemanticEvent?.stage || 'idle');
  const lastWithParagraph = useMemo(
    () => [...events].reverse().find((e) => e.paragraph_idx && e.total_paragraphs),
    [events]
  );
  const totalParagraphs = lastWithParagraph?.total_paragraphs || 0;
  const roundEvent = [...events].reverse().find((e) => typeof e.round === 'number' && e.round > 0);
  const currentRound = Math.min(Math.max(roundEvent?.round || 1, 1), DISPLAY_ROUNDS);
  const iterativeStageWeight: Record<string, number> = {
    search: 0.2,
    summary: 0.5,
    host: 0.8,
    reflection: 1,
  };
  const stagePosition: Record<string, number> = {
    idle: -1,
    outline: 0,
    search: 1,
    summary: 1,
    host: 1,
    reflection: 1,
    final: 2,
    done: 2,
    failed: 2,
    timeout: 2,
    error: 2,
  };
  const currentStep = stagePosition[status === 'running' ? stageNow : status] ?? -1;
  const iterativeLine = events
    .slice()
    .reverse()
    .find((e) => ['search', 'summary', 'host', 'reflection'].includes(e.stage))?.message;
  const iterativeProgress =
    currentStep < 1
      ? 0
      : currentStep >= 2
        ? 1
        : Math.min(((currentRound - 1) + (iterativeStageWeight[stageNow] ?? 0.1)) / DISPLAY_ROUNDS, 0.98);
  const iterativeLogs = events
    .filter((e) => ['search', 'summary', 'host', 'reflection'].includes(e.stage))
    .slice(-ITERATIVE_LOG_LIMIT);

  const activePreview = previewRunId ? previewReport : report;
  const previewQuery = (previewRunId ? previewTitle : query).trim();
  const copy = PIPELINE_COPY['English (US)'];
  const visibleHistory = recentExpanded ? history : history.slice(0, RECENT_COLLAPSED_COUNT);
  const hasMoreHistory = recentExpanded && history.length < historyTotal;
  const previewTarget = useMemo(
    () => history.find((h) => h.run_id === previewRunId) || null,
    [history, previewRunId]
  );
  const currentRunTarget = runId ? { run_id: runId, query: query || 'Research query', status } : null;
  const reportTarget = previewTarget || currentRunTarget;

  const loadMoreHistory = () => {
    if (history.length >= historyTotal) return;
    loadHistory(historyPage + 1, true);
  };

  return (
    <section className="panel research-panel">
      <div className="module-head divider-soft pb-4">
        <h2>Research Run</h2>
        <p className="ui-font">Pose a question; the agent decomposes, searches, critiques, and drafts a report.</p>
      </div>

      <div className="research-layout">
        <div className="research-main">
          <div className="research-input-section">
            {briefAnchorId ? (
              <div className="brief-anchor-banner ui-font">
                <span>Brief anchor active: #{briefAnchorId}</span>
                <button className="ghost" onClick={() => setBriefAnchorId(null)} disabled={status === 'running'}>
                  Clear Anchor
                </button>
              </div>
            ) : null}
            <div className="research-input-wrap">
              <input
                className="research-query-input custom-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && status !== 'running') startRun();
                }}
                placeholder="What do you want to research?"
              />
              <button className="research-start-btn" onClick={startRun} disabled={status === 'running'}>
                {status === 'running' ? 'Running...' : 'Start Research ↵'}
              </button>
            </div>
          </div>

          {notice && <div className="notice">{notice}</div>}

          <div className="card pipeline-reading-card">
            <h4 className="section-eyebrow">{copy.pipelineTitle}</h4>
            <div className="pipeline-timeline">
              <div className={`timeline-item ${currentStep > 0 ? 'done' : currentStep === 0 ? 'active' : 'pending'}`}>
                <h5 style={{ fontFamily: 'var(--font-ui)' }}>{copy.decompositionTitle}</h5>
                <p>{totalParagraphs > 0 ? copy.decompositionDone(totalParagraphs) : copy.decompositionPending}</p>
                {currentStep >= 0 && <span className="highlight-mark">{copy.completed}</span>}
              </div>

              <div className={`timeline-item ${currentStep > 1 ? 'done' : currentStep === 1 ? 'active' : 'pending'}`}>
                <h5 style={{ fontFamily: 'var(--font-ui)' }}>{copy.iterativeTitle}</h5>
                {iterativeLine && <p>{iterativeLine}</p>}
                {currentStep >= 1 && (
                  <div className="ink-meter" style={{ marginTop: '8px' }}>
                    <span style={{ width: `${iterativeProgress * 100}%` }} />
                  </div>
                )}
                {currentStep >= 1 && (
                  <span className="highlight-mark" style={{ display: 'inline-block', marginTop: '6px', marginLeft: 0 }}>
                    {copy.roundLabel} {currentRound}/{DISPLAY_ROUNDS}
                  </span>
                )}
                <div className="log compact-log" id="research-log">
                  {iterativeLogs.length > 0 ? (
                    iterativeLogs.map((e, idx) => (
                      <div key={idx} className="log-line">
                        <strong>[{copy.iterativeStageLabels[e.stage as keyof IterativeLabels] || e.stage}]</strong> {e.message}
                      </div>
                    ))
                  ) : null}
                </div>
              </div>

              <div className={`timeline-item ${currentStep === 2 ? 'active' : currentStep > 2 ? 'done' : 'pending'}`}>
                <h5 style={{ fontFamily: 'var(--font-ui)' }}>{copy.synthesisTitle}</h5>
                {currentStep >= 2 && (
                  <p>{status === 'running' ? copy.synthesisRunning : copy.synthesisDone}</p>
                )}
              </div>
            </div>
          </div>

          <div className="card report-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h4 className="section-eyebrow" style={{ margin: 0 }}>{copy.reportPreview}</h4>
              <div className="report-toolbar" style={{ margin: 0 }}>
                <button className="ghost" onClick={() => reportTarget && openReport(reportTarget)} disabled={!reportTarget}>
                  Full Report
                </button>
                {reportTarget && (
                  <button className="ghost-link" onClick={() => downloadReportPdf(reportTarget.run_id)}>
                    Export PDF
                  </button>
                )}
                {previewRunId && (
                  <button className="ghost" onClick={clearPreview}>
                    Clear
                  </button>
                )}
              </div>
            </div>

            {previewLoading && <div className="muted">Loading preview...</div>}
            {!previewLoading && activePreview ? (
              <div className="report-paper deep-paper">
                <div className="report-paper-head ui-font">
                  <span style={{ fontFamily: 'var(--font-serif)', fontSize: '14px', fontWeight: 'bold', color: 'var(--text-primary)' }}>{previewQuery || 'Research query'}</span>
                  <span>{new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                </div>
                <div className="report-preview-md"><MarkdownViewer content={activePreview} /></div>
                <div className="report-watermark mono">REF: {previewRunId || runId || 'N/A'}</div>
              </div>
            ) : (
              !previewLoading && <div className="muted" style={{ padding: '24px', background: 'var(--bg-sidebar)', border: '1px solid var(--border-color)', borderRadius: '4px' }}>No report yet.</div>
            )}
          </div>
        </div>

        <aside className="research-rail">
          <div className="card recent-runs-collapsible">
            <div className="recent-runs-head">
              <h4 className="section-eyebrow" style={{ margin: 0 }}>
                {copy.recentRuns} ({historyTotal})
              </h4>
            </div>

            <div className="source-list recent-runs-list">
              {visibleHistory.map((h) => (
                <button
                  type="button"
                  key={h.run_id}
                  className={`source-item brief-history-item recent-run-item ${previewRunId === h.run_id ? 'active' : ''}`}
                  onClick={() => previewFromHistory(h)}
                >
                  <div className="recent-run-main">
                    <div className="recent-run-title" style={{ fontFamily: 'var(--font-serif)' }}>{h.query}</div>
                    <div className="source-meta ui-font">{formatRunTimestamp(h)}</div>
                  </div>
                </button>
              ))}
              {history.length === 0 && <div className="muted">{copy.noHistory}</div>}
            </div>

            <div className="recent-runs-footer">
              {hasMoreHistory && (
                <button className="ghost" onClick={loadMoreHistory}>
                  {copy.loadMore}
                </button>
              )}
              <button className="ghost" onClick={() => setRecentExpanded((prev) => !prev)}>
                {recentExpanded ? copy.collapse : copy.expand}
              </button>
            </div>
          </div>
        </aside>
      </div>

      {isReportOpen && (
        <div className="report-modal">
          <div className="report-modal-content">
            <div className="report-modal-header">
              <div>
                <div className="eyebrow">Full Report</div>
                <h3 style={{ fontFamily: 'var(--font-serif)' }}>{selectedRun?.query || 'Report'}</h3>
              </div>
              <div className="report-modal-actions">
                {selectedRun && <button onClick={() => downloadReportPdf(selectedRun.run_id)}>Download PDF</button>}
                <button onClick={closeReport}>Close</button>
              </div>
            </div>
            {reportLoading ? (
              <div className="muted">Loading report...</div>
            ) : (
              <MarkdownViewer content={fullReport || 'No report content.'} />
            )}
          </div>
        </div>
      )}
    </section>
  );
}
