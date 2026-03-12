const API = '/api/proxy';

export const apiFetch = (path: string, init: RequestInit = {}) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return fetch(`${API}${normalizedPath}`, {
    ...init,
    cache: 'no-store',
  });
};

export const markdownToPlainText = (input: string): string => {
  if (!input) return '';
  let text = input.replace(/\r\n/g, '\n');
  // Remove YAML front matter when present.
  text = text.replace(/^\s*---\n[\s\S]*?\n---\n?/m, '');
  text = text.replace(/```[\s\S]*?```/g, (m) => m.replace(/```/g, '').trim());
  text = text.replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1');
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  text = text.replace(/^\s{0,3}#{1,6}\s*/gm, '');
  text = text.replace(/^\s{0,3}>\s?/gm, '');
  text = text.replace(/^\s{0,3}[-*+]\s+/gm, '');
  text = text.replace(/^\s{0,3}\d+\.\s+/gm, '');
  text = text.replace(/`([^`]+)`/g, '$1');
  text = text.replace(/\*\*([^*]+)\*\*/g, '$1');
  text = text.replace(/\*([^*]+)\*/g, '$1');
  text = text.replace(/__([^_]+)__/g, '$1');
  text = text.replace(/_([^_]+)_/g, '$1');
  text = text.replace(/^\s*([-*_]){3,}\s*$/gm, '');
  // Normalize "Sources" heading and keep only plain lines.
  text = text.replace(/^\s*sources\s*$/gim, 'Sources');
  text = text.replace(/\n{3,}/g, '\n\n');
  return text.trim();
};

export const downloadPdfResponse = async (
  res: Response,
  fallbackFilename: string
): Promise<string | null> => {
  if (!res.ok) {
    return await readErrorMessage(res, 'PDF export failed.');
  }

  const contentType = (res.headers.get('Content-Type') || '').toLowerCase();
  if (!contentType.includes('application/pdf')) {
    try {
      const text = (await res.text()).trim();
      return text || 'PDF export failed: invalid response type.';
    } catch {
      return 'PDF export failed: invalid response type.';
    }
  }

  const blob = await res.blob();
  if (!blob || blob.size === 0) {
    return 'PDF export failed: empty file.';
  }

  const disposition = res.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename="?([^"]+)"?/i);
  const filename = decodeURIComponent((match?.[1] || match?.[2] || fallbackFilename).trim());
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return null;
};

export const readErrorMessage = async (res: Response, fallback: string): Promise<string> => {
  try {
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const data = await res.json();
      return data?.message || data?.detail || fallback;
    }
    const text = (await res.text()).trim();
    return text || fallback;
  } catch {
    return fallback;
  }
};

export type RunEvent = {
  stage: string;
  message: string;
  paragraph?: string;
  paragraph_idx?: number;
  total_paragraphs?: number;
  round?: number;
};
export type RunSummary = {
  run_id: string;
  query: string;
  status: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
  source_count?: number;
};

export type Topic = {
  id: number;
  name: string;
  keywords: string[];
  rss_sources: string[];
  scrape_frequency_hours: number;
  push_time: string;
  push_channels: string[];
  is_active: boolean;
};

export type Article = {
  id: number;
  topic_id: number;
  title: string;
  url: string;
  content: string;
  source: string;
  published_at: string | null;
  created_at: string;
  time_source?: 'published_at' | 'fallback(created_at)';
};

export type Brief = {
  id: number;
  topic_id: number;
  date: string;
  content: string;
  item_count: number;
  created_at?: string;
};

export type RecentBrief = Brief & {
  topic_name: string;
};

export type SystemStatus = {
  started_at: string | null;
  scheduler_running: boolean;
  active_research: number;
  max_concurrent_research: number;
  active_chat?: number;
  max_concurrent_chat?: number;
  max_reflections: number;
  rate_limit_backend?: string;
  rate_limit_per_min: number;
  public_rate_limit_per_min?: number;
  public_read_rate_limit_per_min?: number;
  public_export_rate_limit_per_min?: number;
  run_route_limit_per_min?: number;
  chat_route_limit_per_min?: number;
  search_provider_configured?: string;
  search_provider_effective?: string;
  search_provider_fallback?: string;
  search_llm_assisted?: boolean;
  jobs: { id: string; next_run: string | null; trigger: string }[];
};

export type RssHealthEntry = {
  id: number;
  topic_id: number;
  rss_url: string;
  status: string;
  items_fetched: number;
  last_error: string | null;
  last_checked_at: string;
  topic_name?: string;
};

export type AppConfig = {
  strict_academic_mode: boolean;
  critical_analysis_layer: boolean;
  cognitive_model: string;
  report_language: string;
  primary_model: string;
  search_provider: string;
  brief_generation_framework?: string;
  research_recency_mode?: string;
  entity_watchlist: string;
};

export type StarterPackPreviewTopic = {
  name: string;
  rss_count: number;
  keyword_groups: number;
};

export type StarterPack = {
  id: string;
  name: string;
  ideal_for: string;
  focus: string;
  content_types: string[];
  signal_density: string;
  recommended_language: string;
  topics: StarterPackPreviewTopic[];
};

export const PIPELINE_STAGES = [
  { key: 'outline', label: 'Outline' },
  { key: 'search_provider', label: 'Search Provider' },
  { key: 'search', label: 'Search' },
  { key: 'search_window', label: 'Evidence Window' },
  { key: 'search_fallback', label: 'Search Fallback' },
  { key: 'summary', label: 'Summary' },
  { key: 'host', label: 'Host Critique' },
  { key: 'reflection', label: 'Reflection' },
  { key: 'final', label: 'Final Format' },
  { key: 'error', label: 'Error' },
];

export const TOPIC_COLORS = [
  { bg: '#fef3c7', border: '#f59e0b', text: '#92400e' },
  { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' },
  { bg: '#d1fae5', border: '#10b981', text: '#065f46' },
  { bg: '#fae8ff', border: '#d946ef', text: '#86198f' },
  { bg: '#fee2e2', border: '#ef4444', text: '#991b1b' },
  { bg: '#e0e7ff', border: '#6366f1', text: '#3730a3' },
];

export const getTopicColor = (idx: number) => TOPIC_COLORS[idx % TOPIC_COLORS.length];

export const toCsv = (list: string[]) => list.join(', ');
