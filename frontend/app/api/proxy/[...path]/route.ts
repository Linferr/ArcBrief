import { createHmac } from 'node:crypto';
import { isIP } from 'node:net';
import { NextRequest } from 'next/server';

const API_BASE = (process.env.ARCBRIEF_PROXY_API_BASE || 'http://localhost:8000/api').replace(/\/$/, '');
const GUEST_API_KEY = (process.env.ARCBRIEF_PROXY_API_KEY || '').trim();
const ADMIN_API_KEY = (process.env.ARCBRIEF_PROXY_ADMIN_KEY || '').trim();
const SIGNING_SECRET = (process.env.ARCBRIEF_PROXY_SIGNING_SECRET || '').trim();
const READ_ONLY = process.env.ARCBRIEF_PUBLIC_READ_ONLY === '1';

const PUBLIC_GET_ALLOWLIST = [
  /^\/health$/,
  /^\/topics$/,
  /^\/briefs\/recent$/,
  /^\/briefs\/\d+\/export$/,
  /^\/briefs\/\d+\/export\/pdf$/,
];

const READ_ONLY_GET_ALLOWLIST = [
  /^\/history$/,
  /^\/report\/[^/]+$/,
  /^\/report\/[^/]+\/export\/pdf$/,
  /^\/briefs\/\d+\/history$/,
  /^\/topics\/\d+\/articles$/,
  /^\/starter-packs$/,
  /^\/system\/status$/,
  /^\/config$/,
  /^\/rss-health$/,
];

const GUEST_POST_ALLOWLIST = [/^\/run$/, /^\/chat$/];

type RouteKind = 'public_get' | 'guest_post' | 'admin' | 'forbidden';

function classifyRoute(method: string, path: string): RouteKind {
  if (method === 'GET' && PUBLIC_GET_ALLOWLIST.some((p) => p.test(path))) return 'public_get';
  if (READ_ONLY && method === 'GET' && READ_ONLY_GET_ALLOWLIST.some((p) => p.test(path))) {
    return 'public_get';
  }
  if (!READ_ONLY && method === 'POST' && GUEST_POST_ALLOWLIST.some((p) => p.test(path))) {
    return 'guest_post';
  }
  if (!READ_ONLY && ADMIN_API_KEY) return 'admin';
  return 'forbidden';
}

function buildTargetUrl(path: string, search: string): string {
  return `${API_BASE}${path}${search || ''}`;
}

function normalizePath(pathParts: string[]): string {
  if (!pathParts.length) return '/';
  return `/${pathParts.join('/')}`;
}

function extractClientIp(request: NextRequest): string | null {
  const headerCandidates = [
    request.headers.get('x-vercel-forwarded-for'),
    request.headers.get('x-forwarded-for'),
    request.headers.get('cf-connecting-ip'),
    request.headers.get('x-real-ip'),
  ];
  for (const candidate of headerCandidates) {
    if (!candidate) continue;
    const ip = candidate.split(',')[0].trim();
    if (isIP(ip)) return ip;
  }
  return null;
}

function signClientIp(ip: string): { ts: string; sig: string } {
  const ts = Math.floor(Date.now() / 1000).toString();
  const sig = createHmac('sha256', SIGNING_SECRET).update(`${ip}.${ts}`).digest('hex');
  return { ts, sig };
}

function forbiddenResponse(): Response {
  return Response.json(
    { error_code: 'PROXY_FORBIDDEN', message: 'This route is not available in public proxy mode.' },
    { status: 403 }
  );
}

function readOnlyResponse(): Response {
  return Response.json(
    {
      error_code: 'READ_ONLY_DEMO',
      message: 'This public demo is read-only. Live research and chat are disabled.',
    },
    { status: 403 }
  );
}

async function proxy(request: NextRequest, pathParts: string[]): Promise<Response> {
  const method = request.method.toUpperCase();
  const path = normalizePath(pathParts);
  if (method === 'OPTIONS') return new Response(null, { status: 204 });

  const kind = classifyRoute(method, path);
  if (kind === 'forbidden') {
    if (READ_ONLY && method === 'POST') return readOnlyResponse();
    return forbiddenResponse();
  }

  const headers = new Headers();
  const incomingType = request.headers.get('content-type');
  if (incomingType) headers.set('content-type', incomingType);
  const incomingAccept = request.headers.get('accept');
  if (incomingAccept) headers.set('accept', incomingAccept);

  if (kind === 'guest_post') {
    if (!GUEST_API_KEY) {
      return Response.json(
        { error_code: 'PROXY_MISCONFIGURED', message: 'ARCBRIEF_PROXY_API_KEY is missing for guest POST routes.' },
        { status: 500 }
      );
    }
    headers.set('X-API-Key', GUEST_API_KEY);
  } else if (kind === 'admin') {
    headers.set('X-API-Key', ADMIN_API_KEY);
  }

  if (SIGNING_SECRET) {
    const ip = extractClientIp(request);
    if (ip) {
      const { ts, sig } = signClientIp(ip);
      headers.set('X-Arcbrief-Client-Ip', ip);
      headers.set('X-Arcbrief-Client-Ts', ts);
      headers.set('X-Arcbrief-Client-Sig', sig);
    }
  }

  const target = buildTargetUrl(path, request.nextUrl.search);
  const init: RequestInit = {
    method,
    headers,
    redirect: 'manual',
  };
  if (!['GET', 'HEAD'].includes(method)) {
    init.body = await request.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const passthroughHeaders = new Headers(upstream.headers);
  passthroughHeaders.delete('content-encoding');
  passthroughHeaders.delete('transfer-encoding');
  passthroughHeaders.delete('connection');

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: passthroughHeaders,
  });
}

function routeHandler(request: NextRequest, params: { path?: string[] }) {
  return proxy(request, params.path || []);
}

export async function GET(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return routeHandler(request, await context.params);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return routeHandler(request, await context.params);
}

export async function PUT(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return routeHandler(request, await context.params);
}

export async function PATCH(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return routeHandler(request, await context.params);
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return routeHandler(request, await context.params);
}

export async function OPTIONS(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return routeHandler(request, await context.params);
}
