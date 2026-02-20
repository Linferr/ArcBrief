'use client';

import { useEffect, useMemo, useState } from 'react';
import { apiFetch, downloadPdfResponse, markdownToPlainText, readErrorMessage, RunEvent, RunSummary } from './api';

interface Props {
  onRunningChange?: (running: boolean) => void;
  pendingQuery?: string;
  onPendingQueryConsumed?: () => void;
}

export default function ResearchPanel({ onRunningChange, pendingQuery, onPendingQueryConsumed }: Props) {
  const [query, setQuery] = useState('');
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState('idle');
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [report, setReport] = useState('');
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyStatus, setHistoryStatus] = useState<'all' | 'running' | 'done' | 'failed'>('all');
  const [historyQuery, setHistoryQuery] = useState('');
  const [selectedRun, setSelectedRun] = useState<RunSummary | null>(null);
  const [fullReport, setFullReport] = useState('');
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [maxReflections, setMaxReflections] = useState(3);
  const [previewRunId, setPreviewRunId] = useState<string | null>(null);
  const [previewTitle, setPreviewTitle] = useState('');
  const [previewReport, setPreviewReport] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    onRunningChange?.(status === 'running');
  }, [status, onRunningChange]);

  useEffect(() => {
    if (status !== 'running') { setElapsedSeconds(0); return; }
    const timer = setInterval(() => setElapsedSeconds(s => s + 1), 1000);
    return () => clearInterval(timer);
  }, [status]);

  useEffect(() => {
    if (pendingQuery) {
      setQuery(pendingQuery);
      onPendingQueryConsumed?.();
    }
  }, [pendingQuery, onPendingQueryConsumed]);

  const formatElapsed = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  const loadHistory = async (
    page = 1,
    statusFilter = historyStatus,
    keywordFilter = historyQuery
  ) => {
    try {
      const params = new URLSearchParams();
      params.set('page', String(page));
      params.set('size', '10');
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (keywordFilter.trim()) params.set('q', keywordFilter.trim());
      const res = await apiFetch(`/history?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setHistory(data.results || []);
        setHistoryTotal(data.total || 0);
        setHistoryPage(data.page || 1);
      }
    } catch {}
  };

  useEffect(() => {
    loadHistory();
    apiFetch('/system/status')
      .then(r => r.ok ? r.json() : null)
      .then(d => d?.max_reflections && setMaxReflections(d.max_reflections))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadHistory(1, historyStatus, historyQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyStatus]);

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
        body: JSON.stringify({ query: cleanQuery }),
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

  const closeReport = () => { setIsReportOpen(false); setSelectedRun(null); setFullReport(''); };

  const downloadReportPdf = async (targetRunId: string) => {
    try {
      const res = await apiFetch(`/report/${targetRunId}/export/pdf`);
      const error = await downloadPdfResponse(res, `${targetRunId}.pdf`);
      if (error) setNotice(error);
    } catch {
      setNotice('PDF export failed.');
    }
  };

  const stages = useMemo(() => events.map(e => e.stage), [events]);
  const stageNow = stages[stages.length - 1] || 'idle';
  const lastWithParagraph = useMemo(
    () => [...events].reverse().find(e => e.paragraph_idx && e.total_paragraphs),
    [events]
  );
  const totalParagraphs = lastWithParagraph?.total_paragraphs || 1;
  const totalRounds = (maxReflections || 3) + 1;
  const currentRound = Math.min(lastWithParagraph?.round || 1, totalRounds);
  const stageWeight: Record<string, number> = {
    outline: 0.05,
    search: 0.25,
    summary: 0.6,
    host: 0.75,
    reflection: 0.9,
    final: 1,
    error: 1,
  };
  const base = ((lastWithParagraph?.paragraph_idx || 1) - 1) * totalRounds + (currentRound - 1);
  const progress = Math.min(
    (base + (stageWeight[stageNow] ?? 0.1)) / (totalParagraphs * totalRounds),
    1
  );
  const stageLabelMap: Record<string, string> = {
    outline: 'Outline',
    search: 'Search',
    summary: 'Summary',
    host: 'Host Critique',
    reflection: 'Reflection',
    final: 'Final',
    error: 'Error',
  };
  const progressLabel = lastWithParagraph
    ? `Paragraph ${lastWithParagraph.paragraph_idx}/${totalParagraphs} | ${stageLabelMap[stageNow] || stageNow} (Round ${currentRound}/${totalRounds})`
    : `Stage: ${stageLabelMap[stageNow] || stageNow}`;
  const activePreview = previewRunId ? previewReport : report;
  const previewQuery = (previewRunId ? previewTitle : query).trim();
  const compactQuery = previewQuery.length > 72 ? `${previewQuery.slice(0, 72)}...` : previewQuery;
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
  const extractionLine = events
    .slice()
    .reverse()
    .find((e) => ['search', 'summary', 'host', 'reflection'].includes(e.stage))?.message;

  return (
    <section className="panel research-panel">
      <div className="module-head divider-soft pb-4">
        <h2>Research Run</h2>
        <p className="ui-font">Pose a question; the agent decomposes, searches, critiques, and drafts a report.</p>
      </div>

      <div className="research-input-section">
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

      <div className="grid-two">
        <div className="card pipeline-reading-card">
          <h4 className="section-eyebrow">Pipeline Progress</h4>
          <div className="pipeline-meta ui-font">
            <span><strong>Status:</strong> {status}</span>
            <span><strong>Stage:</strong> {stageNow}</span>
            {status === 'running' && <span><strong>Elapsed:</strong> {formatElapsed(elapsedSeconds)}</span>}
            <span className="pipeline-query"><strong>Query Agent:</strong> {compactQuery || 'N/A'}</span>
          </div>
          <div className="pipeline-timeline">
            <div className={`timeline-item ${currentStep > 0 ? 'done' : currentStep === 0 ? 'active' : 'pending'}`}>
              <h5 style={{ fontFamily: 'var(--font-ui)' }}>Query Decomposition</h5>
              <p>
                {currentStep >= 0 ? `Mapped into ${totalParagraphs} analysis segments.` : 'Awaiting run start.'}
                {currentStep >= 0 && <span className="highlight-mark">Completed</span>}
              </p>
            </div>
            <div className={`timeline-item ${currentStep > 1 ? 'done' : currentStep === 1 ? 'active' : 'pending'}`}>
              <h5 style={{ fontFamily: 'var(--font-ui)' }}>Deep Web Extraction</h5>
              <p>{extractionLine || 'Collecting evidence across sources.'}</p>
              <div className="ink-meter" style={{ marginTop: '8px' }}>
                <span style={{ width: `${Math.max(progress, 0.05) * 100}%` }} />
              </div>
              {currentStep >= 1 && <span className="highlight-mark" style={{ display: 'inline-block', marginTop: '6px', marginLeft: 0 }}>Round {currentRound}/{totalRounds}</span>}
            </div>
            <div className={`timeline-item ${currentStep === 2 ? 'active' : currentStep > 2 ? 'done' : 'pending'}`}>
              <h5 style={{ fontFamily: 'var(--font-ui)' }}>Synthesis & Reporting</h5>
              <p>{currentStep >= 2 ? 'Composing final narrative and citations.' : 'Waiting for extraction...'}</p>
            </div>
          </div>
          <div className="muted pipeline-label ui-font" style={{ marginTop: '16px' }}>{progressLabel}</div>
          <div className="log compact-log" id="research-log">
            {events.slice(-8).map((e, idx) => (
              <div key={idx} className="log-line">
                <strong>[{e.stage}]</strong> {e.message}
              </div>
            ))}
          </div>
        </div>

        <div className="card report-card" style={{ padding: '0', background: 'transparent', border: 'none' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h4 className="section-eyebrow" style={{ margin: 0 }}>Report Preview</h4>
            <div className="report-toolbar" style={{ margin: 0 }}>
              <button className="ghost" onClick={() => runId && openReport({ run_id: runId, query, status })} disabled={!runId}>
                Full Report
              </button>
              {runId && (
                <button className="ghost-link" onClick={() => downloadReportPdf(runId)}>
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
              <pre className="report-preview" style={{ fontFamily: 'var(--font-serif)' }}>{markdownToPlainText(activePreview).split('\n').slice(0, 22).join('\n')}</pre>
              <div className="report-watermark mono">REF: {previewRunId || runId || 'N/A'}</div>
            </div>
          ) : (
            !previewLoading && <div className="muted" style={{ padding: '24px', background: 'var(--bg-sidebar)', border: '1px solid var(--border-color)', borderRadius: '4px' }}>No report yet.</div>
          )}
        </div>
      </div>

      <div className="card history" style={{ marginTop: '32px' }}>
        <div className="history-head divider-soft pb-2">
          <h3 style={{ fontFamily: 'var(--font-serif)' }}>Recent Runs ({historyTotal} total)</h3>
          <div className="history-filters ui-font">
            <select
              value={historyStatus}
              onChange={(e) => setHistoryStatus(e.target.value as 'all' | 'running' | 'done' | 'failed')}
            >
              <option value="all">All</option>
              <option value="running">Running</option>
              <option value="done">Done</option>
              <option value="failed">Failed</option>
            </select>
            <input
              value={historyQuery}
              onChange={(e) => setHistoryQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') loadHistory(1, historyStatus, historyQuery);
              }}
              placeholder="Search query..."
            />
            <button className="ghost" onClick={() => loadHistory(1, historyStatus, historyQuery)}>
              Apply
            </button>
          </div>
        </div>
        <div className="history-grid">
          {history.map((h) => (
            <div key={h.run_id} className="history-item clickable" onClick={() => previewFromHistory(h)}>
              <div>
                <div className="history-title" style={{ fontFamily: 'var(--font-serif)' }}>{h.query}</div>
                <div className="muted ui-font">
                  {h.status}
                  {h.created_at ? ` | ${new Date(h.created_at).toLocaleString()}` : ''}
                </div>
              </div>
              <div className="history-actions">
                {h.status === 'failed' && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setQuery(h.query);
                      startRun();
                    }}
                  >
                    Retry
                  </button>
                )}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    openReport(h);
                  }}
                >
                  Full Report
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    downloadReportPdf(h.run_id);
                  }}
                >
                  Export PDF
                </button>
              </div>
            </div>
          ))}
          {history.length === 0 && <div className="muted">No research history yet.</div>}
        </div>
        {historyTotal > 10 && (
          <div className="pagination">
            <button disabled={historyPage <= 1} onClick={() => loadHistory(historyPage - 1)}>
              Prev
            </button>
            <span>
              Page {historyPage} / {Math.ceil(historyTotal / 10)}
            </span>
            <button disabled={historyPage * 10 >= historyTotal} onClick={() => loadHistory(historyPage + 1)}>
              Next
            </button>
          </div>
        )}
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
              <pre className="report-full" style={{ fontFamily: 'var(--font-serif)' }}>{markdownToPlainText(fullReport || 'No report content.')}</pre>
            )}
          </div>
        </div>
      )}
    </section>
  );
}