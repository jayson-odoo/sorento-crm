/**
 * PROJECT-REGISTER-V2 H1: TruncatedTextCell gains `lines` (1 default, 2), shows the full text as
 * the hover title, and offers an eye button "Show full title" ONLY when the text is actually
 * clamped; it opens a dialog with the full text.
 *
 * jsdom has no layout, so the overflow measurement is mocked at the element level: a clamped
 * text reports a scroll size bigger than its client size on both axes (whichever the coder
 * measures), an unclamped one reports equal sizes.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { TruncatedTextCell } from './TruncatedTextCell';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

const LONG =
  'Cadangan pembangunan bercampur CONTOH merangkumi pangsapuri servis, ruang pejabat, kedai runcit dan kemudahan awam di atas tanah seluas sepuluh ekar';

function setOverflow(clamped: boolean) {
  const sizes = clamped
    ? { scrollHeight: 120, clientHeight: 40, scrollWidth: 900, clientWidth: 200 }
    : { scrollHeight: 20, clientHeight: 20, scrollWidth: 200, clientWidth: 200 };
  for (const [key, value] of Object.entries(sizes)) {
    Object.defineProperty(HTMLElement.prototype, key, { configurable: true, get: () => value });
  }
}

beforeEach(() => setOverflow(true));
afterEach(() => {
  for (const key of ['scrollHeight', 'clientHeight', 'scrollWidth', 'clientWidth']) {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>)[key];
  }
});

describe('TruncatedTextCell lines (H1)', () => {
  it('defaults to one line and carries the full text as the hover title', () => {
    render(<TruncatedTextCell text={LONG} />);
    const label = screen.getByTitle(LONG);
    expect(label.className).toMatch(/\btruncate\b|line-clamp-1/);
    expect(label.className).not.toMatch(/line-clamp-2/);
  });

  it('lines={2} clamps to two lines', () => {
    render(<TruncatedTextCell text={LONG} lines={2} />);
    expect(screen.getByTitle(LONG).className).toMatch(/line-clamp-2/);
  });

  it('shows the eye button "Show full title" only when clamped, and it opens the full text', async () => {
    render(<TruncatedTextCell text={LONG} lines={2} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Show full title' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(LONG)).toBeInTheDocument();
  });

  it('shows no eye button when the text fits, however long its string is', async () => {
    setOverflow(false);
    render(<TruncatedTextCell text={LONG} lines={2} />);
    await waitFor(() => expect(screen.getByTitle(LONG)).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Show full title' })).toBeNull();
  });

  it('shows no eye button for a short title that fits', async () => {
    setOverflow(false);
    render(<TruncatedTextCell text="Menara CONTOH" />);
    await waitFor(() => expect(screen.getByTitle('Menara CONTOH')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Show full title' })).toBeNull();
  });
});
