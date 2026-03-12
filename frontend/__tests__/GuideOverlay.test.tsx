import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../app/components/api', () => ({
  apiFetch: vi.fn(),
  downloadPdfResponse: vi.fn(),
  markdownToPlainText: (value: string) => value,
}));

import GuideOverlay from '../app/components/GuideOverlay';
import { apiFetch, type Topic } from '../app/components/api';

const mockedApiFetch = vi.mocked(apiFetch);

const activeTopic = (overrides: Partial<Topic> = {}): Topic => ({
  id: 1,
  name: 'AI Daily',
  keywords: [],
  rss_sources: [],
  scrape_frequency_hours: 4,
  push_time: '08:00',
  push_channels: ['discord'],
  is_active: true,
  ...overrides,
});

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

describe('GuideOverlay', () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    window.localStorage.clear();
  });

  it('shows the first-run overlay when starter setup is incomplete', async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === '/starter-packs') {
        return new Response(
          JSON.stringify([
            {
              id: 'ai-operator',
              name: 'AI Operator Pack',
              ideal_for: 'Founders',
              focus: 'AI product and operations',
              content_types: ['blogs', 'release notes'],
              signal_density: 'high',
              recommended_language: 'English (US)',
              topics: [{ name: 'AI Daily', rss_count: 4, keyword_groups: 3 }],
            },
          ]),
          { status: 200 },
        );
      }
      if (path === '/briefs/recent?limit=200') {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });

    const onNavigateSettings = vi.fn();

    render(
      <GuideOverlay
        topics={[]}
        deepActionStarted={false}
        onNavigateDailyBrief={() => {}}
        onNavigateSettings={onNavigateSettings}
        onNavigateArchive={() => {}}
        onSendToResearch={() => {}}
        onOpenTopicBrief={() => {}}
      />,
    );

    expect(await screen.findByText('Apply a starter pack')).toBeInTheDocument();
    expect(screen.getByText(/AI Operator Pack/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Open Settings/i }));
    expect(onNavigateSettings).toHaveBeenCalled();
  });

  it('hides the auto-overlay after completion and reopens a compact guide from the floating button', async () => {
    window.localStorage.setItem('guide_pack_completed', '1');
    window.localStorage.setItem('guide_brief_completed', '1');
    window.localStorage.setItem('guide_deep_action_completed', '1');

    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === '/starter-packs') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
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
                content: richBriefContent,
                item_count: 4,
              },
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
      return new Response(JSON.stringify([]), { status: 200 });
    });

    const onSendToResearch = vi.fn();
    const onOpenTopicBrief = vi.fn();

    render(
      <GuideOverlay
        topics={[activeTopic()]}
        deepActionStarted
        onNavigateDailyBrief={() => {}}
        onNavigateSettings={() => {}}
        onNavigateArchive={() => {}}
        onSendToResearch={onSendToResearch}
        onOpenTopicBrief={onOpenTopicBrief}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByText('Apply a starter pack')).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Open guide/i }));

    expect(await screen.findByText("Today's Next Action")).toBeInTheDocument();
    expect(screen.getByText('Revisit Queue')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Start Guide Again/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Send to Research/i }));
    expect(onSendToResearch).toHaveBeenCalledWith(
      'What are the most actionable implications from the latest AI Daily brief?',
    );

    fireEvent.click(screen.getAllByRole('button', { name: /Open Topic Brief/i })[0]);
    expect(onOpenTopicBrief).toHaveBeenCalled();
  });
});
