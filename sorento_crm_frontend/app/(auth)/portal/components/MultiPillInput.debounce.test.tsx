/**
 * M6-06 - MultiPillInput adopts useDebouncedSearch (was a hand-rolled 250ms
 * setTimeout). It keeps its own pill/chip input, only the debounce mechanism
 * changes, plus a "Searching..." label while the box is ahead of the query.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MultiPillInput } from './MultiPillInput';

describe('MultiPillInput debounce', () => {
  it('fetches once typing settles, and shows "Searching..." meanwhile', async () => {
    let resolveFetch: (v: { value: string; label: string }[]) => void = () => {};
    const fetchOptions = vi.fn(
      () =>
        new Promise<{ value: string; label: string }[]>((resolve) => {
          resolveFetch = resolve;
        }),
    );
    render(<MultiPillInput value="" onChange={vi.fn()} fetchOptions={fetchOptions} />);

    const input = screen.getByRole('textbox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'ab' } });

    // Ahead of the query: settling, so the box says so even before the
    // network request is made.
    await screen.findByText('Searching...');

    await waitFor(() => expect(fetchOptions).toHaveBeenCalledWith('ab'));

    resolveFetch([{ value: 'ab-1', label: 'AB One' }]);
    await screen.findByText('AB One');
    expect(screen.queryByText('Searching...')).not.toBeInTheDocument();
  });

  it('rapid keystrokes settle on the FINAL value, not one fetch per keystroke', async () => {
    // Opening the box fetches once for the empty query (pre-existing
    // behaviour, unchanged by the debounce swap); typing three characters in
    // one breath must not add three more - only the value they settled on.
    const fetchOptions = vi.fn().mockResolvedValue([]);
    render(<MultiPillInput value="" onChange={vi.fn()} fetchOptions={fetchOptions} />);

    const input = screen.getByRole('textbox');
    fireEvent.focus(input);
    await waitFor(() => expect(fetchOptions).toHaveBeenCalledWith(''));
    fetchOptions.mockClear();

    fireEvent.change(input, { target: { value: 'a' } });
    fireEvent.change(input, { target: { value: 'ab' } });
    fireEvent.change(input, { target: { value: 'abc' } });

    await waitFor(() => expect(fetchOptions).toHaveBeenCalledWith('abc'));
    expect(fetchOptions).toHaveBeenCalledTimes(1);
  });
});
