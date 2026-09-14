/**
 * A request's design history sheet (r9 S5/D19, AC-S5-6).
 *
 * Newest first, because a list that grows downwards buries the version
 * somebody wants. Restore runs immediately with no confirmation - it ADDS a
 * version ("Restored v<n>") rather than destroying one, so the way back is the
 * list itself, which is exactly the case ADR-PRODUCT-STANDARDS says must not
 * grow a dialog.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';

import RequestVersionsSheet from './RequestVersionsSheet';
import type { RequestVersionSummary } from '@/lib/dealer-kit/product-data-changes';

const toasts = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

const VERSIONS: RequestVersionSummary[] = [
  {
    version: 3,
    commit_message: 'Marked proof ready',
    created_by_name: 'ZZT Marketing Mei',
    created_at: '2026-09-14T02:00:00Z',
  },
  {
    version: 2,
    commit_message: 'Before product update: List price',
    created_by_name: 'ZZT Marketing Mei',
    created_at: '2026-09-13T02:00:00Z',
  },
  {
    version: 1,
    commit_message: null,
    created_by_name: null,
    created_at: '2026-09-12T02:00:00Z',
  },
];

function renderSheet(overrides: Partial<React.ComponentProps<typeof RequestVersionsSheet>> = {}) {
  const load = vi.fn(async () => VERSIONS);
  const onView = vi.fn();
  const onRestore = vi.fn(async () => {});
  const result = render(
    <RequestVersionsSheet
      open
      onOpenChange={vi.fn()}
      docNumber="PT-202609-0001"
      load={load}
      onView={onView}
      onRestore={onRestore}
      {...overrides}
    />,
  );
  return { ...result, load, onView, onRestore };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('the list (AC-S5-6)', () => {
  it('loads on open and lists newest first', async () => {
    const { load } = renderSheet();

    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    const rows = await screen.findAllByText(/^Version \d+$/);
    expect(rows.map((row) => row.textContent)).toEqual([
      'Version 3',
      'Version 2',
      'Version 1',
    ]);
  });

  it('names the request it is about', async () => {
    renderSheet();

    expect(await screen.findByText(/PT-202609-0001/)).toBeInTheDocument();
  });

  it('says who saved each version and what they called it', async () => {
    renderSheet();

    expect(await screen.findByText('Marked proof ready')).toBeInTheDocument();
    expect(
      screen.getByText('Before product update: List price'),
    ).toBeInTheDocument();
    // An unnamed save is still readable rather than blank.
    expect(screen.getByText('No note')).toBeInTheDocument();
    expect(screen.getByText(/Unknown/)).toBeInTheDocument();
  });

  it('an empty history says what would create the first version', async () => {
    renderSheet({ load: vi.fn(async () => []) });

    expect(
      await screen.findByText(/Saving the design writes the first one/),
    ).toBeInTheDocument();
  });

  it('a failed load reports and leaves the sheet usable', async () => {
    renderSheet({
      load: vi.fn(async () => {
        throw new Error('Failed to load the history');
      }),
    });

    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith('Failed to load the history'),
    );
  });
});

describe('View and Restore (AC-S5-6)', () => {
  it('View opens that version, by number', async () => {
    const { onView } = renderSheet();
    const row = await screen.findByTestId('request-version-2');

    fireEvent.click(within(row).getByRole('button', { name: /View/ }));

    expect(onView).toHaveBeenCalledWith(2);
  });

  it('Restore runs straight away with no confirmation dialog', async () => {
    const { onRestore } = renderSheet();
    const row = await screen.findByTestId('request-version-1');

    fireEvent.click(within(row).getByRole('button', { name: /Restore/ }));

    await waitFor(() => expect(onRestore).toHaveBeenCalledWith(1));
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('reloads the list afterwards, because Restore adds a version', async () => {
    const { load, onRestore } = renderSheet();
    await screen.findByTestId('request-version-1');
    expect(load).toHaveBeenCalledTimes(1);

    fireEvent.click(
      within(screen.getByTestId('request-version-1')).getByRole('button', {
        name: /Restore/,
      }),
    );

    await waitFor(() => expect(onRestore).toHaveBeenCalled());
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });
});
