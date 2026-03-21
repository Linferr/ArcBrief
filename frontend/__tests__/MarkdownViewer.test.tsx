import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import MarkdownViewer, { normalizeMarkdownForVariant } from '../app/components/MarkdownViewer';

describe('MarkdownViewer citation rendering', () => {
  it('renders (C1) as a superscript citation', () => {
    render(<MarkdownViewer content="Some claim (C1)" />);
    const citation = screen.getByText('(C1)');
    expect(citation.tagName).toBe('SUP');
    expect(citation.className).toContain('md-citation');
  });

  it('renders multi-citation (C2, C5) as a single superscript', () => {
    render(<MarkdownViewer content="Evidence here (C2, C5)" />);
    const citation = screen.getByText('(C2, C5)');
    expect(citation.tagName).toBe('SUP');
    expect(citation.className).toContain('md-citation');
  });

  it('renders [S1] source anchor as superscript', () => {
    render(<MarkdownViewer content="Key finding [S1]" />);
    const citation = screen.getByText('[S1]');
    expect(citation.tagName).toBe('SUP');
    expect(citation.className).toContain('md-citation');
  });

  it('does not convert normal parentheses or brackets to citations', () => {
    render(<MarkdownViewer content="normal (text) and [data] here" />);
    // These should be plain text, not inside <sup>
    const container = document.querySelector('.md-viewer');
    expect(container).toBeTruthy();
    const sups = container!.querySelectorAll('sup.md-citation');
    expect(sups.length).toBe(0);
  });

  it('only converts citation patterns in mixed content', () => {
    render(<MarkdownViewer content="Claim here (C1) and normal (text) after" />);
    const sups = document.querySelectorAll('sup.md-citation');
    expect(sups.length).toBe(1);
    expect(sups[0].textContent).toBe('(C1)');
  });

  it('applies the brief variant class when requested', () => {
    render(<MarkdownViewer content="## Brief\n\nParagraph" variant="brief" />);
    expect(document.querySelector('.md-viewer-brief')).toBeTruthy();
  });

  it('compresses excessive blank lines in brief mode without changing default mode', () => {
    expect(normalizeMarkdownForVariant('A\r\n\r\n\r\n\r\nB', 'brief')).toBe('A\n\n\nB');
    expect(normalizeMarkdownForVariant('A\r\n\r\n\r\n\r\nB', 'default')).toBe('A\n\n\n\nB');
  });
});
