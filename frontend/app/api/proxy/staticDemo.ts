type DemoRecord = Record<string, unknown>;

export type DemoSnapshot = {
  generated_at: string;
  topics: DemoRecord[];
  briefs_recent: { count: number; items: DemoRecord[] };
  brief_history: Record<string, DemoRecord[]>;
  articles_by_date: Record<string, Record<string, DemoRecord[]>>;
  history: { total: number; page: number; size: number; results: DemoRecord[] };
  reports: Record<string, string>;
  feedback: Record<string, { upvotes: number; downvotes: number }>;
  starter_packs: DemoRecord[];
  config: DemoRecord;
  rss_health: { sources: DemoRecord[] };
  system_status: DemoRecord;
};

export type StaticDemoResult =
  | { kind: 'json'; status: number; body: unknown }
  | { kind: 'text'; status: number; body: string; contentType: string }
  | { kind: 'redirect'; location: string }
  | { kind: 'error'; status: number; error_code: string; message: string };

const json = (body: unknown): StaticDemoResult => ({ kind: 'json', status: 200, body });

const notFound = (message: string): StaticDemoResult => ({
  kind: 'error',
  status: 404,
  error_code: 'STATIC_DEMO_NOT_FOUND',
  message,
});

const clamp = (raw: string | null, fallback: number, min: number, max: number): number => {
  const parsed = Number.parseInt(raw || '', 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, min), max);
};

export function resolveStaticDemoRoute(
  snapshot: DemoSnapshot,
  method: string,
  rawPath: string,
  params: URLSearchParams
): StaticDemoResult {
  if (method.toUpperCase() !== 'GET') {
    return {
      kind: 'error',
      status: 403,
      error_code: 'READ_ONLY_DEMO',
      message: 'This public demo is read-only. Live research and chat are disabled.',
    };
  }

  const path = rawPath.length > 1 ? rawPath.replace(/\/+$/, '') : rawPath;

  if (path === '/health') {
    return json({ status: 'ok', mode: 'static-demo', generated_at: snapshot.generated_at });
  }
  if (path === '/topics') return json(snapshot.topics);
  if (path === '/starter-packs') return json(snapshot.starter_packs);
  if (path === '/system/status') return json(snapshot.system_status);
  if (path === '/config') return json(snapshot.config);
  if (path === '/rss-health') return json(snapshot.rss_health);

  if (path === '/briefs/recent') {
    const limit = clamp(params.get('limit'), 40, 1, 200);
    const topicId = params.get('topic_id');
    const items = snapshot.briefs_recent.items
      .filter((item) => !topicId || String(item.topic_id) === topicId)
      .slice(0, limit);
    return json({ count: items.length, items });
  }

  const briefHistory = path.match(/^\/briefs\/(\d+)\/history$/);
  if (briefHistory) {
    const limit = clamp(params.get('limit'), 7, 1, 30);
    const items = (snapshot.brief_history[briefHistory[1]] || []).slice(0, limit);
    return json(items);
  }

  const briefFeedback = path.match(/^\/briefs\/(\d+)\/feedback$/);
  if (briefFeedback) {
    return json(snapshot.feedback[briefFeedback[1]] || { upvotes: 0, downvotes: 0 });
  }

  const briefPdf = path.match(/^\/briefs\/(\d+)\/export\/pdf$/);
  if (briefPdf) {
    const exists = snapshot.briefs_recent.items.some(
      (item) => String(item.id) === briefPdf[1]
    );
    return exists
      ? { kind: 'redirect', location: `/demo/pdfs/briefs/${briefPdf[1]}.pdf` }
      : notFound('Brief not found');
  }

  const topicArticles = path.match(/^\/topics\/(\d+)\/articles$/);
  if (topicArticles) {
    const topicId = topicArticles[1];
    const date = params.get('date') || '';
    const topic = snapshot.topics.find((item) => String(item.id) === topicId);
    const articles = snapshot.articles_by_date[topicId]?.[date] || [];
    return json({
      topic_id: Number(topicId),
      topic_name: topic?.name || '',
      count: articles.length,
      articles,
    });
  }

  if (path === '/history') {
    const status = params.get('status');
    const query = (params.get('q') || '').toLowerCase();
    const filtered = snapshot.history.results.filter((item) => {
      if (status && item.status !== status) return false;
      if (query && !String(item.query || '').toLowerCase().includes(query)) return false;
      return true;
    });
    const page = clamp(params.get('page'), 1, 1, Number.MAX_SAFE_INTEGER);
    const size = clamp(params.get('size'), 10, 1, 50);
    const start = (page - 1) * size;
    return json({
      total: filtered.length,
      page,
      size,
      results: filtered.slice(start, start + size),
    });
  }

  const reportPdf = path.match(/^\/report\/([^/]+)\/export\/pdf$/);
  if (reportPdf) {
    const runId = reportPdf[1];
    return snapshot.reports[runId]
      ? { kind: 'redirect', location: `/demo/pdfs/reports/${runId}.pdf` }
      : notFound('Report not found');
  }

  const report = path.match(/^\/report\/([^/]+)$/);
  if (report) {
    const content = snapshot.reports[report[1]];
    if (!content) return notFound('Report not found');
    return { kind: 'text', status: 200, body: content, contentType: 'text/plain; charset=utf-8' };
  }

  return notFound(`No static demo data for ${path}`);
}
