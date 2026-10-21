// @vitest-environment node

import { resolveStaticDemoRoute, DemoSnapshot } from '../app/api/proxy/staticDemo';

const snapshot: DemoSnapshot = {
  generated_at: '2026-03-21T00:00:00',
  topics: [
    { id: 3, name: 'AI Daily', keywords: ['ai'], rss_sources: [], is_active: true },
    { id: 4, name: 'Macro and Metals', keywords: ['gold'], rss_sources: [], is_active: false },
  ],
  briefs_recent: {
    count: 2,
    items: [
      { id: 11, topic_id: 3, topic_name: 'AI Daily', date: '2026-03-20', content: 'brief a', item_count: 2 },
      { id: 12, topic_id: 4, topic_name: 'Macro and Metals', date: '2026-03-19', content: 'brief b', item_count: 1 },
    ],
  },
  brief_history: {
    '3': [{ id: 11, topic_id: 3, date: '2026-03-20', content: 'brief a', item_count: 2 }],
  },
  articles_by_date: {
    '3': {
      '2026-03-20': [
        {
          id: 1,
          topic_id: 3,
          title: 'Agent launch',
          url: 'https://example.com/agent',
          content: 'body',
          source: 'example.com',
          published_at: '2026-03-20T10:00:00',
          created_at: '2026-03-20T10:00:00',
        },
      ],
    },
  },
  history: {
    total: 3,
    page: 1,
    size: 10,
    results: [
      { run_id: 'run_a', query: 'OpenAI news', status: 'done', started_at: '2026-03-20T10:00:00' },
      { run_id: 'run_b', query: 'AI policy', status: 'done', started_at: '2026-03-19T10:00:00' },
      { run_id: 'run_c', query: 'Agent tooling', status: 'done', started_at: '2026-03-18T10:00:00' },
    ],
  },
  reports: {
    run_a: '# OpenAI news\n\nBody',
    run_b: '# AI policy\n\nBody',
    run_c: '# Agent tooling\n\nBody',
  },
  feedback: { '11': { upvotes: 2, downvotes: 0 } },
  starter_packs: [{ id: 'ai-coding', name: 'AI Coding', topics: [] }],
  config: { report_language: 'English (US)', entity_watchlist: '' },
  rss_health: { sources: [{ id: 1, rss_url: 'https://example.com/feed', status: 'ok' }] },
  system_status: { scheduler_running: false, active_research: 0, jobs: [] },
};

const get = (path: string, query = '') =>
  resolveStaticDemoRoute(snapshot, 'GET', path, new URLSearchParams(query));

describe('static demo proxy', () => {
  it('serves topics from the snapshot', () => {
    const result = get('/topics');

    expect(result.kind).toBe('json');
    if (result.kind !== 'json') return;
    expect(result.status).toBe(200);
    expect(result.body).toEqual(snapshot.topics);
  });

  it('filters recent briefs by topic and limit', () => {
    const result = get('/briefs/recent', 'topic_id=3&limit=1');

    expect(result.kind).toBe('json');
    if (result.kind !== 'json') return;
    expect(result.body).toMatchObject({ count: 1 });
    expect((result.body as { items: unknown[] }).items).toHaveLength(1);
  });

  it('serves stored brief history regardless of the requested time window', () => {
    const result = get('/briefs/3/history', 'limit=30&since_hours=168');

    expect(result.kind).toBe('json');
    if (result.kind !== 'json') return;
    expect(result.body).toEqual(snapshot.brief_history['3']);
  });

  it('serves dated articles for a topic', () => {
    const result = get('/topics/3/articles', 'date=2026-03-20&sort=time');

    expect(result.kind).toBe('json');
    if (result.kind !== 'json') return;
    expect(result.body).toMatchObject({ topic_id: 3, topic_name: 'AI Daily', count: 1 });
    expect((result.body as { articles: unknown[] }).articles).toHaveLength(1);
  });

  it('serves report markdown as plain text', () => {
    const result = get('/report/run_a');

    expect(result.kind).toBe('text');
    if (result.kind !== 'text') return;
    expect(result.contentType).toBe('text/plain; charset=utf-8');
    expect(result.body).toBe('# OpenAI news\n\nBody');
  });

  it('paginates research history from the snapshot', () => {
    const result = get('/history', 'page=2&size=2');

    expect(result.kind).toBe('json');
    if (result.kind !== 'json') return;
    expect(result.body).toMatchObject({ total: 3, page: 2, size: 2 });
    expect((result.body as { results: unknown[] }).results).toHaveLength(1);
  });

  it('redirects PDF exports to bundled static files', () => {
    expect(get('/report/run_a/export/pdf')).toEqual({
      kind: 'redirect',
      location: '/demo/pdfs/reports/run_a.pdf',
    });
    expect(get('/briefs/11/export/pdf')).toEqual({
      kind: 'redirect',
      location: '/demo/pdfs/briefs/11.pdf',
    });
  });

  it('rejects every write route', () => {
    const result = resolveStaticDemoRoute(snapshot, 'POST', '/run', new URLSearchParams());

    expect(result).toMatchObject({ kind: 'error', status: 403, error_code: 'READ_ONLY_DEMO' });
  });

  it('returns 404 for paths outside the static surface', () => {
    const result = get('/status/run_a');

    expect(result).toMatchObject({ kind: 'error', status: 404, error_code: 'STATIC_DEMO_NOT_FOUND' });
  });
});
