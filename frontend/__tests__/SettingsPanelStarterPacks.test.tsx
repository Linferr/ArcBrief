import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../app/components/api', () => ({
  apiFetch: vi.fn(),
  getTopicColor: () => ({ bg: '#fff', border: '#000', text: '#000' }),
  toCsv: (items: string[]) => items.join(', '),
}));

import SettingsPanel from '../app/components/SettingsPanel';
import { apiFetch } from '../app/components/api';

const mockedApiFetch = vi.mocked(apiFetch);

describe('SettingsPanel starter packs', () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it('renders starter pack preview metadata and applies a pack', async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === '/system/status') {
        return new Response(JSON.stringify({ started_at: null, scheduler_running: true, active_research: 0, max_concurrent_research: 3, jobs: [] }), { status: 200 });
      }
      if (path === '/starter-packs') {
        return new Response(JSON.stringify([
          {
            id: 'ai-founder-daily',
            name: 'AI Founder Daily',
            ideal_for: 'AI founder',
            focus: 'Models, builders, policy',
            content_types: ['daily digest', 'product launch'],
            signal_density: 'High',
            recommended_language: 'English (US)',
            topics: [
              { name: 'AI Daily', rss_count: 5, keyword_groups: 3 },
              { name: 'AI Builder Signals', rss_count: 4, keyword_groups: 2 },
            ],
          },
        ]), { status: 200 });
      }
      if (path === '/rss-health') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (path === '/config') {
        return new Response(JSON.stringify({ report_language: 'English (US)', primary_model: 'Qwen3 MAX', search_provider: 'Tavily Search API', strict_academic_mode: false, critical_analysis_layer: false, cognitive_model: 'Neutral (Fact-first)', entity_watchlist: '' }), { status: 200 });
      }
      if (path === '/starter-packs/apply') {
        return new Response(JSON.stringify({ pack_id: 'ai-founder-daily', created_count: 2, existing_topics: [], created_topics: ['AI Daily', 'AI Builder Signals'] }), { status: 200 });
      }
      return new Response(null, { status: 404 });
    });

    const onTopicsChange = vi.fn();
    render(<SettingsPanel topics={[]} onTopicsChange={onTopicsChange} />);

    expect(await screen.findByText('Starter Packs')).toBeInTheDocument();
    expect(screen.getByText('AI Founder Daily')).toBeInTheDocument();
    expect(screen.getByText((content, element) => element?.textContent === 'AI founder')).toBeInTheDocument();
    expect(screen.getByText(/Models, builders, policy/i)).toBeInTheDocument();
    expect(screen.getByText(/AI Daily · 5 RSS · 3 keyword groups/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /apply pack/i }));

    await waitFor(() => {
      expect(onTopicsChange).toHaveBeenCalled();
    });

    expect(mockedApiFetch).toHaveBeenCalledWith('/starter-packs/apply', expect.objectContaining({
      method: 'POST',
    }));
  });
});
