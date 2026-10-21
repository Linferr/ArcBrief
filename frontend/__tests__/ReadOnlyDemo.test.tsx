import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../app/components/api', () => ({
  apiFetch: vi.fn(),
  downloadPdfResponse: vi.fn().mockResolvedValue(null),
  readErrorMessage: vi.fn(async (res: Response, fallback: string) => {
    try {
      const text = await res.text();
      return text || fallback;
    } catch {
      return fallback;
    }
  }),
}));

import ResearchPanel from '../app/components/ResearchPanel';
import { apiFetch } from '../app/components/api';
import { isReadOnlyDemo } from '../app/components/demoMode';

const mockedApiFetch = vi.mocked(apiFetch);

describe('read-only demo UI', () => {
  const previousValue = process.env.NEXT_PUBLIC_ARCBRIEF_READ_ONLY;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_ARCBRIEF_READ_ONLY = '1';
    mockedApiFetch.mockReset();
  });

  afterEach(() => {
    if (previousValue === undefined) delete process.env.NEXT_PUBLIC_ARCBRIEF_READ_ONLY;
    else process.env.NEXT_PUBLIC_ARCBRIEF_READ_ONLY = previousValue;
  });

  it('reads the public flag', () => {
    expect(isReadOnlyDemo()).toBe(true);
    process.env.NEXT_PUBLIC_ARCBRIEF_READ_ONLY = '0';
    expect(isReadOnlyDemo()).toBe(false);
  });

  it('hides the research composer but keeps stored reports readable', async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === '/history?page=1&size=10') {
        return new Response(
          JSON.stringify({
            results: [
              {
                run_id: 'demo-run',
                query: 'Demo history query',
                status: 'done',
                created_at: '2026-03-20T10:00:00Z',
              },
            ],
            total: 1,
            page: 1,
          }),
          { status: 200 },
        );
      }
      if (path === '/report/demo-run') {
        return new Response('DEMO REPORT BODY', { status: 200 });
      }
      return new Response(null, { status: 404 });
    });

    render(<ResearchPanel isVisible />);

    expect(screen.queryByPlaceholderText(/what do you want to research/i)).not.toBeInTheDocument();
    expect(screen.getByText(/live research is disabled/i)).toBeInTheDocument();

    const historyButton = await screen.findByText('Demo history query');
    fireEvent.click(historyButton.closest('button')!);

    const dialog = await screen.findByRole('dialog', { name: /demo history query/i });
    expect(dialog).toHaveTextContent('DEMO REPORT BODY');
    await waitFor(() => {
      expect(mockedApiFetch).not.toHaveBeenCalledWith('/config');
    });
  });
});
