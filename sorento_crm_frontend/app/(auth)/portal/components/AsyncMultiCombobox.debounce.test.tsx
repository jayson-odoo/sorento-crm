/**
 * M6-06 - AsyncMultiCombobox adopts useDebouncedSearch (was a hand-rolled
 * 300ms setTimeout). It keeps its own combobox input, only the debounce
 * mechanism changes, plus a "Searching..." label while the box is ahead of
 * the query.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AsyncMultiCombobox } from './AsyncMultiCombobox';

type Item = { id: string; name: string };

describe('AsyncMultiCombobox debounce', () => {
  it('fetches once typing settles, and shows "Searching..." meanwhile', async () => {
    let resolveFetch: (v: Item[]) => void = () => {};
    const fetchOptions = vi.fn(
      () =>
        new Promise<Item[]>((resolve) => {
          resolveFetch = resolve;
        }),
    );
    render(
      <AsyncMultiCombobox<Item>
        value={[]}
        onChange={vi.fn()}
        fetchOptions={fetchOptions}
        optionValue={(o) => o.id}
        optionLabel={(o) => o.name}
      />,
    );

    const input = screen.getByRole('textbox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'ab' } });

    await screen.findByText('Searching...');
    await waitFor(() => expect(fetchOptions).toHaveBeenCalledWith('ab'));

    resolveFetch([{ id: 'ab-1', name: 'AB One' }]);
    await screen.findByText('AB One');
    expect(screen.queryByText('Searching...')).not.toBeInTheDocument();
  });

  it('rapid keystrokes settle on the FINAL value', async () => {
    const fetchOptions = vi.fn().mockResolvedValue([]);
    render(
      <AsyncMultiCombobox<Item>
        value={[]}
        onChange={vi.fn()}
        fetchOptions={fetchOptions}
        optionValue={(o) => o.id}
        optionLabel={(o) => o.name}
      />,
    );

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
