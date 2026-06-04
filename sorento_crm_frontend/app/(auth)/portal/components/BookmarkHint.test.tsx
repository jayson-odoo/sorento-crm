import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { BookmarkHint } from './BookmarkHint';

beforeEach(() => {
  window.localStorage.clear();
});

describe('BookmarkHint', () => {
  it('renders on first visit and dismisses persistently', async () => {
    const { unmount } = render(<BookmarkHint />);
    await waitFor(() =>
      expect(screen.getByTestId('bookmark-hint')).toBeTruthy(),
    );
    fireEvent.click(screen.getByLabelText('Dismiss bookmark hint'));
    expect(screen.queryByTestId('bookmark-hint')).toBeNull();
    unmount();

    // Re-mount: stays dismissed (localStorage flag)
    render(<BookmarkHint />);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('bookmark-hint')).toBeNull();
  });

  it('copies the stable URL (origin + pathname, no query)', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    window.history.pushState({}, '', '/portal/c/SLUG123456?type=complaint');

    render(<BookmarkHint />);
    await waitFor(() =>
      expect(screen.getByTestId('bookmark-copy')).toBeTruthy(),
    );
    fireEvent.click(screen.getByTestId('bookmark-copy'));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied.endsWith('/portal/c/SLUG123456')).toBe(true);
    expect(copied).not.toContain('?type');
  });

  it('hides the share button when navigator.share is unavailable', async () => {
    render(<BookmarkHint />);
    await waitFor(() =>
      expect(screen.getByTestId('bookmark-hint')).toBeTruthy(),
    );
    expect(screen.queryByTestId('bookmark-share')).toBeNull();
  });
});
