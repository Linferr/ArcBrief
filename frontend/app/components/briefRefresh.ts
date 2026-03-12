'use client';

import { apiFetch, readErrorMessage } from './api';

export type BriefRefreshSummary = {
  collected: number;
  saved: number;
  duplicates: number;
  totalTopics?: number;
};

export async function runBriefRefreshAll(language?: string): Promise<{
  ok: boolean;
  summary?: BriefRefreshSummary;
  error?: string;
}> {
  const collectRes = await apiFetch('/topics/collect_all', { method: 'POST' });
  if (!collectRes.ok) {
    return {
      ok: false,
      error: await readErrorMessage(collectRes, 'Collection failed.'),
    };
  }

  const collectData = await collectRes.json();
  const body = language ? JSON.stringify({ language }) : undefined;
  const briefRes = await apiFetch('/topics/brief_all', {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body,
  });
  if (!briefRes.ok) {
    return {
      ok: false,
      error: await readErrorMessage(briefRes, 'Brief generation failed.'),
    };
  }

  const briefData = await briefRes.json();
  return {
    ok: true,
    summary: {
      collected: collectData.total_collected || 0,
      saved: collectData.total_saved || 0,
      duplicates: collectData.total_duplicates || 0,
      totalTopics: briefData.total_topics || 0,
    },
  };
}
