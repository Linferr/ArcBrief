import { fireEvent, render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../app/components/api', () => ({
  apiFetch: vi.fn(),
  downloadPdfResponse: vi.fn(),
  markdownToPlainText: (value: string) => value,
}));

import NewsFeedPanel from '../app/components/NewsFeedPanel';
import { apiFetch } from '../app/components/api';

const mockedApiFetch = vi.mocked(apiFetch);

const briefContent = (sourceCount: number) =>
  [
    '## Synthesis',
    '### Daily Executive Summary',
    '**Signal headline**',
    'A strong synthesis summary.',
    '**Key Takeaways**',
    '- One',
    '- Two',
    '*Sentiment: neutral | Reliability: high*',
    '(Related articles: 12)',
    '## 1. Builder shifts',
    '### AI Daily',
    '**Builders are moving fast**',
    'Detailed cluster summary.',
    '**Key Takeaways**',
    '- Cluster takeaway',
    '## Sources',
    ...Array.from({ length: sourceCount }, (_, idx) => `- Item ${idx + 1} [Source ${idx + 1}] (2026-03-10) [published_at]`),
  ].join('\n');

describe('NewsFeedPanel revisit recommendations', () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it('surfaces a revisit queue and routes archive/topic actions', async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === '/briefs/recent?limit=200') {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 11,
                topic_id: 1,
                topic_name: 'AI Daily',
                date: '2026-03-11',
                created_at: '2026-03-11T10:00:00Z',
                content: briefContent(2),
                item_count: 4,
              },
              {
                id: 10,
                topic_id: 1,
                topic_name: 'AI Daily',
                date: '2026-03-10',
                created_at: '2026-03-10T10:00:00Z',
                content: briefContent(9),
                item_count: 12,
              },
            ],
          }),
          { status: 200 },
        );
      }
      if (path === '/briefs/1/history?limit=30&since_hours=168') {
        return new Response(
          JSON.stringify([
            {
              id: 11,
              topic_id: 1,
              date: '2026-03-11',
              created_at: '2026-03-11T10:00:00Z',
              content: briefContent(2),
              item_count: 4,
            },
          ]),
          { status: 200 },
        );
      }
      if (path === '/briefs/11/feedback') {
        return new Response(JSON.stringify({ upvotes: 0, downvotes: 0 }), { status: 200 });
      }
      if (path.startsWith('/topics/1/articles?')) {
        return new Response(JSON.stringify({ articles: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({ items: [] }), { status: 200 });
    });

    const onNavigateArchive = vi.fn();
    render(
      <NewsFeedPanel
        topics={[
          {
            id: 1,
            name: 'AI Daily',
            keywords: [],
            rss_sources: [],
            scrape_frequency_hours: 4,
            push_time: '08:00',
            push_channels: ['discord'],
            is_active: true,
          },
        ]}
        onNavigateSettings={() => {}}
        onNavigateArchive={onNavigateArchive}
        onSendToResearch={() => {}}
      />,
    );

    expect(await screen.findByText(/Revisit Queue/i)).toBeInTheDocument();
    expect(screen.getByText(/stronger evidence than the latest cycle/i)).toBeInTheDocument();

    const revisitCard = screen.getByText(/Revisit Queue/i).closest('.revisit-card');
    expect(revisitCard).not.toBeNull();
    const revisitScope = within(revisitCard as HTMLElement);

    fireEvent.click(revisitScope.getByRole('button', { name: /Open Archive/i }));
    expect(onNavigateArchive).toHaveBeenCalled();

    fireEvent.click(revisitScope.getByRole('button', { name: /Open Topic Brief/i }));
    expect(await screen.findByText(/Synthesis Brief/i)).toBeInTheDocument();
  });
});
