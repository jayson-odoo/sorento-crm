/**
 * SnippetPicker - list states + the two pure helpers (UAC AC-L4, slice S4.4).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import SnippetPicker, { activeSlashFragment, filterSnippets } from './SnippetPicker';
import type { MessageSnippetOption } from '@/app/(protected)/sla-management/message-snippets/types/messageSnippet.types';

function option(over: Partial<MessageSnippetOption> = {}): MessageSnippetOption {
  return {
    id: 's1',
    name: 'Stock check',
    shortcut: 'stock',
    body: 'Hi $contact_name, we are checking stock.',
    resolved_body: 'Hi Aisyah Rahman, we are checking stock.',
    ...over,
  };
}

describe('activeSlashFragment', () => {
  it('opens on a slash at the very start', () => {
    expect(activeSlashFragment('/', 1)).toEqual({ start: 0, query: '' });
    expect(activeSlashFragment('/sto', 4)).toEqual({ start: 0, query: 'sto' });
  });

  it('stays shut for a slash anywhere else', () => {
    // A date, a URL and "and/or" are text a person is writing, not a command.
    expect(activeSlashFragment('due 15/08', 9)).toBeNull();
    expect(activeSlashFragment('see https://x/y', 15)).toBeNull();
    expect(activeSlashFragment('and/or', 6)).toBeNull();
  });

  it('gives up once the text stops looking like a keyword', () => {
    expect(activeSlashFragment('/stock check now please', 23)).toEqual({
      start: 0,
      query: 'stock check now please',
    });
    expect(activeSlashFragment('/line\nbreak', 11)).toBeNull();
    expect(activeSlashFragment(`/${'x'.repeat(60)}`, 61)).toBeNull();
  });

  it('reads only up to the caret', () => {
    expect(activeSlashFragment('/stock', 3)).toEqual({ start: 0, query: 'st' });
  });
});

describe('filterSnippets', () => {
  const items = [option(), option({ id: 's2', name: 'Delivery ETA', shortcut: 'eta' })];

  it('matches on the name', () => {
    expect(filterSnippets(items, 'deliv').map((s) => s.id)).toEqual(['s2']);
  });

  it('matches on the shortcut', () => {
    expect(filterSnippets(items, 'stoc').map((s) => s.id)).toEqual(['s1']);
  });

  it('is case-insensitive and returns everything on an empty query', () => {
    expect(filterSnippets(items, 'ETA').map((s) => s.id)).toEqual(['s2']);
    expect(filterSnippets(items, '  ')).toHaveLength(2);
  });

  it('returns nothing when nothing matches', () => {
    expect(filterSnippets(items, 'zzz')).toEqual([]);
  });
});

describe('SnippetPicker', () => {
  const noop = () => {};

  it('renders each snippet with its resolved preview, never the raw token', () => {
    render(
      <SnippetPicker
        items={[option()]}
        isLoading={false}
        activeIndex={0}
        onActiveIndexChange={noop}
        onPick={noop}
      />,
    );

    expect(screen.getByText('Stock check')).toBeInTheDocument();
    expect(screen.getByText('/stock')).toBeInTheDocument();
    expect(screen.getByText('Hi Aisyah Rahman, we are checking stock.')).toBeInTheDocument();
    expect(screen.queryByText(/\$contact_name/)).not.toBeInTheDocument();
  });

  it('shows a loading row before anything has arrived', () => {
    render(
      <SnippetPicker
        items={[]}
        isLoading
        activeIndex={0}
        onActiveIndexChange={noop}
        onPick={noop}
      />,
    );
    expect(screen.getByText('Loading snippets')).toBeInTheDocument();
  });

  it('shows the empty state when the filter matches nothing', () => {
    render(
      <SnippetPicker
        items={[]}
        isLoading={false}
        activeIndex={0}
        onActiveIndexChange={noop}
        onPick={noop}
      />,
    );
    expect(screen.getByTestId('snippet-picker-empty')).toBeInTheDocument();
  });

  it('shows the error instead of pretending the list is empty', () => {
    render(
      <SnippetPicker
        items={[]}
        isLoading={false}
        error="Failed to load snippets"
        activeIndex={0}
        onActiveIndexChange={noop}
        onPick={noop}
      />,
    );
    expect(screen.getByTestId('snippet-picker-error')).toHaveTextContent('Failed to load snippets');
  });

  it('picks on mouse DOWN, because a blur would close it before a click lands', () => {
    const onPick = vi.fn();
    render(
      <SnippetPicker
        items={[option()]}
        isLoading={false}
        activeIndex={0}
        onActiveIndexChange={noop}
        onPick={onPick}
      />,
    );

    fireEvent.mouseDown(screen.getByTestId('snippet-option'));

    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: 's1' }));
  });

  it('marks the active row for the keyboard', () => {
    render(
      <SnippetPicker
        items={[option(), option({ id: 's2', name: 'Delivery ETA' })]}
        isLoading={false}
        activeIndex={1}
        onActiveIndexChange={noop}
        onPick={noop}
      />,
    );

    const rows = screen.getAllByRole('option');
    expect(rows[0]).toHaveAttribute('aria-selected', 'false');
    expect(rows[1]).toHaveAttribute('aria-selected', 'true');
  });
});
