import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, '..');
const SNAPSHOT_PATH = path.join(FRONTEND, 'demo-data', 'snapshot.json');
const PDF_ROOT = path.join(FRONTEND, 'public', 'demo', 'pdfs');
const EDGE =
  process.env.EDGE_PATH ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

if (!fs.existsSync(EDGE)) {
  throw new Error(`Microsoft Edge not found at ${EDGE}. Set EDGE_PATH to the executable.`);
}
if (!fs.existsSync(SNAPSHOT_PATH)) {
  throw new Error(`Snapshot not found at ${SNAPSHOT_PATH}. Run scripts/build_demo_snapshot.py first.`);
}

const snapshot = JSON.parse(fs.readFileSync(SNAPSHOT_PATH, 'utf8'));
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'arcbrief-demo-pdfs-'));
const profileDir = path.join(tempRoot, 'edge-profile');

const escapeHtml = (value) =>
  String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

const markdownToHtml = (markdown) =>
  renderToStaticMarkup(
    React.createElement(ReactMarkdown, { remarkPlugins: [remarkGfm] }, markdown || '')
  );

const pageHtml = ({ label, title, subtitle, markdown }) => `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(title)}</title>
<style>
  @page { size: A4; margin: 18mm 16mm 20mm; }
  * { box-sizing: border-box; }
  body {
    font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    color: #1f2933;
    font-size: 11.5pt;
    line-height: 1.62;
    margin: 0;
  }
  .doc-label {
    font-size: 9pt;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #b45309;
    font-weight: 700;
    margin-bottom: 10px;
  }
  h1.doc-title {
    font-size: 24pt;
    line-height: 1.22;
    margin: 0 0 8px;
    color: #0f172a;
    page-break-after: avoid;
  }
  .doc-subtitle {
    color: #64748b;
    font-size: 10pt;
    margin-bottom: 18px;
    padding-bottom: 14px;
    border-bottom: 2px solid #f1f5f9;
  }
  h1, h2, h3, h4 { color: #0f172a; page-break-after: avoid; }
  h1 { font-size: 18pt; margin-top: 24px; }
  h2 { font-size: 15pt; margin-top: 22px; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; }
  h3 { font-size: 12.5pt; margin-top: 18px; }
  p { margin: 8px 0; }
  a { color: #1d4ed8; text-decoration: none; word-break: break-word; }
  ul, ol { padding-left: 22px; }
  li { margin: 4px 0; }
  blockquote {
    margin: 12px 0;
    padding: 8px 14px;
    border-left: 3px solid #f59e0b;
    background: #fffbeb;
    color: #475569;
  }
  code {
    font-family: "Cascadia Mono", Consolas, monospace;
    background: #f1f5f9;
    border-radius: 3px;
    padding: 1px 4px;
    font-size: 9.5pt;
  }
  pre {
    background: #0f172a;
    color: #e2e8f0;
    padding: 12px 14px;
    border-radius: 6px;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
    font-size: 9pt;
  }
  pre code { background: transparent; color: inherit; padding: 0; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 9.5pt; }
  th, td { border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; vertical-align: top; }
  th { background: #f8fafc; }
  tr { page-break-inside: avoid; }
  hr { border: 0; border-top: 1px solid #e2e8f0; margin: 18px 0; }
  img { max-width: 100%; }
</style>
</head>
<body>
  <div class="doc-label">${escapeHtml(label)}</div>
  <h1 class="doc-title">${escapeHtml(title)}</h1>
  <div class="doc-subtitle">${escapeHtml(subtitle)}</div>
  ${markdownToHtml(markdown)}
</body>
</html>`;

const renderPdf = (htmlPath, pdfPath) =>
  new Promise((resolve, reject) => {
    const child = spawn(
      EDGE,
      [
        '--headless=new',
        '--disable-gpu',
        '--disable-extensions',
        '--disable-background-networking',
        '--no-first-run',
        '--no-default-browser-check',
        '--no-pdf-header-footer',
        `--user-data-dir=${profileDir}`,
        `--print-to-pdf=${pdfPath}`,
        pathToFileURL(htmlPath).href,
      ],
      { stdio: ['ignore', 'ignore', 'pipe'] }
    );
    let stderr = '';
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`Edge exited with ${code}: ${stderr.slice(-500)}`));
        return;
      }
      if (!fs.existsSync(pdfPath) || fs.statSync(pdfPath).size === 0) {
        reject(new Error(`PDF was not written: ${pdfPath}`));
        return;
      }
      resolve();
    });
  });

const writeAndPrint = async ({ label, title, subtitle, markdown, pdfPath, slug }) => {
  const htmlPath = path.join(tempRoot, `${slug}.html`);
  fs.writeFileSync(
    htmlPath,
    pageHtml({ label, title, subtitle, markdown }),
    'utf8'
  );
  fs.mkdirSync(path.dirname(pdfPath), { recursive: true });
  await renderPdf(htmlPath, pdfPath);
  fs.rmSync(htmlPath, { force: true });
};

const topicNames = new Map(snapshot.topics.map((topic) => [String(topic.id), topic.name]));
const reports = snapshot.history.results
  .filter((run) => snapshot.reports[run.run_id])
  .map((run) => ({
    label: 'ArcBrief · Research Report',
    title: run.query || run.run_id,
    subtitle: `${run.started_at || ''}${run.language_used ? ` · ${run.language_used}` : ''} · ${run.run_id}`,
    markdown: snapshot.reports[run.run_id],
    pdfPath: path.join(PDF_ROOT, 'reports', `${run.run_id}.pdf`),
    slug: `report-${run.run_id}`,
  }));
const briefs = snapshot.briefs_recent.items.map((brief) => ({
  label: 'ArcBrief · Daily Brief',
  title: topicNames.get(String(brief.topic_id)) || `Topic ${brief.topic_id}`,
  subtitle: `${brief.date} · ${brief.item_count} source items`,
  markdown: brief.content || '',
  pdfPath: path.join(PDF_ROOT, 'briefs', `${brief.id}.pdf`),
  slug: `brief-${brief.id}`,
}));

fs.rmSync(path.join(PDF_ROOT, 'reports'), { recursive: true, force: true });
fs.rmSync(path.join(PDF_ROOT, 'briefs'), { recursive: true, force: true });

const jobs = [...reports, ...briefs];
console.log(`Rendering ${jobs.length} PDFs (${reports.length} reports, ${briefs.length} briefs)...`);
for (const [index, job] of jobs.entries()) {
  await writeAndPrint(job);
  console.log(`[${index + 1}/${jobs.length}] ${path.relative(FRONTEND, job.pdfPath)}`);
}

fs.rmSync(tempRoot, { recursive: true, force: true });
console.log(`Done. PDFs are in ${path.relative(FRONTEND, PDF_ROOT)}.`);
