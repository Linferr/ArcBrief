import { render, screen } from '@testing-library/react';
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

const richBriefContent = [
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
  '- Item 1 [Source A] (2026-03-10) [published_at]',
  '- Item 2 [Source B] (2026-03-10) [published_at]',
  '- Item 3 [Source C] (2026-03-10) [published_at]',
  '- Item 4 [Source D] (2026-03-10) [published_at]',
  '- Item 5 [Source E] (2026-03-10) [published_at]',
  '- Item 6 [Source F] (2026-03-10) [published_at]',
  '- Item 7 [Source G] (2026-03-10) [published_at]',
  '- Item 8 [Source H] (2026-03-10) [published_at]',
].join('\n');

describe('NewsFeedPanel next action', () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it('keeps the daily brief surface free of onboarding and recommendation cards', async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === '/briefs/recent?limit=200') {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 10,
                topic_id: 1,
                topic_name: 'AI Daily',
                date: '2026-03-10',
                created_at: '2026-03-10T10:00:00Z',
                content: richBriefContent,
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
              id: 10,
              topic_id: 1,
              date: '2026-03-10',
              created_at: '2026-03-10T10:00:00Z',
              content: richBriefContent,
              item_count: 12,
            },
          ]),
          { status: 200 },
        );
      }
      if (path === '/briefs/10/feedback') {
        return new Response(JSON.stringify({ upvotes: 0, downvotes: 0 }), { status: 200 });
      }
      if (path.startsWith('/topics/1/articles?')) {
        return new Response(JSON.stringify({ articles: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({ items: [] }), { status: 200 });
    });

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
        onNavigateArchive={() => {}}
        onSendToResearch={() => {}}
      />,
    );

    expect(await screen.findByText(/All Topics Digest/i)).toBeInTheDocument();
    expect(screen.queryByText(/First-Value Path/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Today's Next Action/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Revisit Queue/i)).not.toBeInTheDocument();
    expect(screen.getAllByText('Healthy').length).toBeGreaterThan(0);
  });
});
