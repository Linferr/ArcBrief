'use client';

import React, { ReactNode } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownViewerProps {
  content: string;
  className?: string;
  variant?: 'default' | 'brief';
}

export function normalizeMarkdownForVariant(
  content: string,
  variant: MarkdownViewerProps['variant'] = 'default',
): string {
  const normalized = (content || '').replace(/\r\n/g, '\n');
  if (variant !== 'brief') return normalized;
  return normalized.replace(/\n{4,}/g, '\n\n\n').trim();
}

const CONFIDENCE_LEVELS: Record<string, { label: string; className: string }> = {
  'HIGH CONFIDENCE': { label: 'HIGH', className: 'md-confidence-high' },
  'MEDIUM CONFIDENCE': { label: 'MEDIUM', className: 'md-confidence-medium' },
  'LOW CONFIDENCE': { label: 'LOW', className: 'md-confidence-low' },
};

/**
 * Replace citation patterns like (C1), (C2, C5), [S1], [S2] with <sup> tags,
 * and [HIGH/MEDIUM/LOW CONFIDENCE] with colored badges.
 */
function renderCitations(text: string): ReactNode[] {
  const pattern = /(\(C\d+(?:,\s*C\d+)*\)|\[S\d+\]|\[(HIGH|MEDIUM|LOW) CONFIDENCE\])/g;
  const parts = text.split(pattern);
  const result: ReactNode[] = [];
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    if (part === undefined || part === '') continue;
    const conf = CONFIDENCE_LEVELS[part.slice(1, -1)];
    if (conf) {
      result.push(
        <span key={i} className={`md-confidence ${conf.className}`}>
          {conf.label}
        </span>
      );
      // skip the captured group from the alternation (HIGH|MEDIUM|LOW)
      i++;
      continue;
    }
    if (/^\(C\d+/.test(part) || /^\[S\d+\]$/.test(part)) {
      result.push(
        <sup key={i} className="md-citation">
          {part}
        </sup>
      );
      continue;
    }
    result.push(part);
  }
  return result;
}

function processCitations(children: ReactNode): ReactNode {
  if (typeof children === 'string') {
    return renderCitations(children);
  }
  if (Array.isArray(children)) {
    return children.map((child, i) => {
      if (typeof child === 'string') {
        return <React.Fragment key={i}>{renderCitations(child)}</React.Fragment>;
      }
      return child;
    });
  }
  return children;
}

const components: Components = {
  p({ children }) {
    return <p>{processCitations(children)}</p>;
  },
  li({ children }) {
    return <li>{processCitations(children)}</li>;
  },
  h2({ children }) {
    return <h2 className="md-h2">{children}</h2>;
  },
  blockquote({ children }) {
    return <blockquote className="md-blockquote">{children}</blockquote>;
  },
  strong({ children }) {
    return <strong className="md-strong">{processCitations(children)}</strong>;
  },
};

export default function MarkdownViewer({
  content,
  className,
  variant = 'default',
}: MarkdownViewerProps) {
  const normalizedContent = normalizeMarkdownForVariant(content, variant);
  const variantClass = variant === 'brief' ? 'md-viewer-brief' : '';
  return (
    <div className={`md-viewer ${variantClass} ${className ?? ''}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
