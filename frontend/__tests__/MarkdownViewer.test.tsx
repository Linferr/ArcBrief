import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import MarkdownViewer from '../app/components/MarkdownViewer';

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
});
