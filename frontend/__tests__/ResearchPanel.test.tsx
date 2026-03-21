import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

const mockedApiFetch = vi.mocked(apiFetch);

const historyRun = {
  run_id: 'run-history',
  query: 'Historical market memo',
  status: 'done',
  created_at: '2026-03-20T10:00:00Z',
};

describe('ResearchPanel history modal behavior', () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  const installApiMock = () => {
    mockedApiFetch.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === '/config') {
        return new Response(JSON.stringify({ report_language: 'English (US)' }), { status: 200 });
      }
      if (path === '/history?page=1&size=10') {
        return new Response(JSON.stringify({ results: [historyRun], total: 1, page: 1 }), { status: 200 });
      }
      if (path === '/run' && init?.method === 'POST') {
        return new Response(JSON.stringify({ run_id: 'run-current' }), { status: 200 });
      }
      if (path === '/status/run-current') {
        return new Response(
          JSON.stringify({
            status: 'done',
            events: [{ stage: 'final', message: 'Final report generated.' }],
            report_content: 'CURRENT PREVIEW REPORT',
          }),
          { status: 200 },
        );
      }
      if (path === '/report/run-history') {
        return new Response('HISTORY MODAL REPORT', { status: 200 });
      }
      if (path === '/report/run-current') {
        return new Response('CURRENT FULL REPORT', { status: 200 });
      }
      return new Response(null, { status: 404 });
    });
  };

  it('opens history entries in the modal and preserves the current preview on the left', async () => {
    installApiMock();

    render(<ResearchPanel isVisible />);

    fireEvent.change(screen.getByPlaceholderText(/what do you want to research/i), {
      target: { value: 'Current research query' },
    });
    fireEvent.click(screen.getByRole('button', { name: /start research/i }));

    await waitFor(() => {
      expect(screen.getByText('CURRENT PREVIEW REPORT')).toBeInTheDocument();
    }, { timeout: 3000 });

    const historyButton = screen.getByText('Historical market memo').closest('button');
    expect(historyButton).toBeTruthy();
    fireEvent.click(historyButton!);

    const dialog = await screen.findByRole('dialog', { name: /historical market memo/i });
    expect(within(dialog).getByText('HISTORY MODAL REPORT')).toBeInTheDocument();
    expect(screen.getByText('CURRENT PREVIEW REPORT')).toBeInTheDocument();
    expect(screen.queryByText(/loading preview/i)).not.toBeInTheDocument();
  });

  it('keeps full report bound to the current run preview', async () => {
    installApiMock();

    render(<ResearchPanel isVisible />);

    fireEvent.change(screen.getByPlaceholderText(/what do you want to research/i), {
      target: { value: 'Current research query' },
    });
    fireEvent.click(screen.getByRole('button', { name: /start research/i }));

    await waitFor(() => {
      expect(screen.getByText('CURRENT PREVIEW REPORT')).toBeInTheDocument();
    }, { timeout: 3000 });

    fireEvent.click(screen.getByRole('button', { name: /full report/i }));

    const dialog = await screen.findByRole('dialog', { name: /current research query/i });
    expect(within(dialog).getByText('CURRENT FULL REPORT')).toBeInTheDocument();
    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith('/report/run-current');
    });
  });
});
