/**
 * AGENT-PANEL-COMPOSER F7: the files a user sent show above their bubble.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import MessageFiles from './MessageFiles';
import type { SentFile } from '@/lib/aiAssistantChatApi';

afterEach(() => cleanup());

function sent(over: Partial<SentFile>): SentFile {
  return {
    id: 'f-1',
    filename: 'people.csv',
    size: 100,
    mime_type: 'text/csv',
    kind: 'sheet',
    sheet: null,
    rows_read: 3,
    rows_total: 3,
    pages: null,
    url: 'https://files.test/people.csv',
    thumb_url: null,
    ...over,
  };
}

describe('MessageFiles', () => {
  it('renders nothing for no files', () => {
    const { container } = render(<MessageFiles files={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('a sheet is a chip linking to its url in a new tab, with its row count', () => {
    render(<MessageFiles files={[sent({ rows_total: 212, rows_read: 50 })]} />);

    const link = screen.getByRole('link', { name: /people\.csv/ });
    expect(link).toHaveAttribute('href', 'https://files.test/people.csv');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(screen.getByText('people.csv')).toBeInTheDocument();
    expect(screen.getByText(/212 rows/)).toBeInTheDocument();
  });

  it('an image shows its thumbnail and opens the url', () => {
    render(
      <MessageFiles
        files={[
          sent({
            id: 'f-2',
            filename: 'shot.png',
            kind: 'image',
            mime_type: 'image/png',
            rows_read: null,
            rows_total: null,
            url: 'https://files.test/shot.png',
            thumb_url: 'https://files.test/shot.thumb.jpg',
          }),
        ]}
      />,
    );

    const img = screen.getByRole('img', { name: 'shot.png' });
    expect(img).toHaveAttribute('src', 'https://files.test/shot.thumb.jpg');
    expect(img.closest('a')).toHaveAttribute('href', 'https://files.test/shot.png');
    expect(img.closest('a')).toHaveAttribute('target', '_blank');
  });

  it('a pdf shows its page count', () => {
    render(
      <MessageFiles
        files={[sent({ id: 'f-3', filename: 'spec.pdf', kind: 'pdf', rows_read: null, rows_total: null, pages: 3, url: 'https://files.test/spec.pdf' })]}
      />,
    );

    expect(screen.getByRole('link', { name: /spec\.pdf/ })).toHaveAttribute('href', 'https://files.test/spec.pdf');
    expect(screen.getByText('3 pages')).toBeInTheDocument();
  });

  it('keeps the order of the files', () => {
    render(
      <MessageFiles
        files={[sent({ id: 'a', filename: 'a.csv' }), sent({ id: 'b', filename: 'b.csv' }), sent({ id: 'c', filename: 'c.csv' })]}
      />,
    );

    expect(screen.getAllByRole('link').map((l) => l.textContent?.slice(0, 5))).toEqual(['a.csv', 'b.csv', 'c.csv']);
  });

  it('shows no id anywhere', () => {
    const { container } = render(<MessageFiles files={[sent({ id: '3f2b8c1e-5d44-4e0a-9a51-0b7e6c1d2f90' })]} />);
    expect(container.textContent).not.toContain('3f2b8c1e');
  });
});
