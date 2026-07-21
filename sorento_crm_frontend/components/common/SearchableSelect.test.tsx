import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import { SearchableSelect, type SearchableSelectOption } from './SearchableSelect';

const OPTIONS: SearchableSelectOption[] = [
  { value: 'kl', label: 'Asia/Kuala Lumpur', searchText: 'Asia/Kuala_Lumpur Asia/Kuala Lumpur' },
  { value: 'nd', label: 'America/North Dakota/Beulah' },
  { value: 'kg', label: 'Europe/Kaliningrad' },
];

const openMenu = () =>
  fireEvent.click(document.querySelector('[data-slot="searchable-select-trigger"]')!);
const search = (text: string) =>
  fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: text } });
const optionLabels = () =>
  [...document.querySelectorAll('[role="option"]')].map((o) => o.textContent?.trim());

beforeEach(() => vi.clearAllMocks());

describe('SearchableSelect filtering', () => {
  it('matches on substring, not cmdk fuzzy subsequence', async () => {
    render(<SearchableSelect value="" onChange={vi.fn()} options={OPTIONS} />);
    openMenu();
    search('kuala');

    // cmdk's scoring also surfaced "North Dakota/Beulah" and "Kaliningrad" here.
    await waitFor(() => expect(optionLabels()).toEqual(['Asia/Kuala Lumpur']));
  });

  it('requires every token to match', async () => {
    render(<SearchableSelect value="" onChange={vi.fn()} options={OPTIONS} />);
    openMenu();
    search('asia lumpur');
    await waitFor(() => expect(optionLabels()).toEqual(['Asia/Kuala Lumpur']));

    search('asia dakota');
    await waitFor(() => expect(optionLabels()).toEqual([]));
  });

  it('reports the query to onSearchChange in static mode', async () => {
    const onSearchChange = vi.fn();
    render(
      <SearchableSelect
        value=""
        onChange={vi.fn()}
        options={OPTIONS}
        onSearchChange={onSearchChange}
      />,
    );
    openMenu();
    search('kal');
    await waitFor(() => expect(onSearchChange).toHaveBeenCalledWith('kal'));
  });
});

describe('SearchableSelect async pagination', () => {
  const page = (n: number, size: number) =>
    Array.from({ length: size }, (_, i) => ({ value: `p${n}-${i}`, label: `Item ${n}-${i}` }));

  it('appends the next page and stops offering more when a short page returns', async () => {
    const fetchOptions = vi
      .fn()
      .mockImplementationOnce(async () => page(0, 2))
      .mockImplementationOnce(async () => page(1, 1));

    render(
      <SearchableSelect
        value=""
        onChange={vi.fn()}
        fetchOptions={fetchOptions}
        paginated
        pageSize={2}
      />,
    );
    openMenu();

    await waitFor(() => expect(optionLabels()).toHaveLength(2));
    const loadMore = () =>
      document.querySelector('[data-slot="searchable-select-load-more"]') as HTMLElement | null;
    expect(loadMore()).toBeTruthy();

    fireEvent.click(loadMore()!);

    // Page 1 appended, and the short page means there is nothing left to load.
    await waitFor(() => expect(optionLabels()).toHaveLength(3));
    await waitFor(() => expect(loadMore()).toBeNull());
    expect(fetchOptions).toHaveBeenNthCalledWith(2, '', 1);
  });

  it('offers no Load more when pagination is off', async () => {
    const fetchOptions = vi.fn().mockResolvedValue(page(0, 50));
    render(<SearchableSelect value="" onChange={vi.fn()} fetchOptions={fetchOptions} />);
    openMenu();

    await waitFor(() => expect(optionLabels()).toHaveLength(50));
    expect(document.querySelector('[data-slot="searchable-select-load-more"]')).toBeNull();
  });
});

describe('SearchableSelect renderTrigger', () => {
  it('replaces the trigger entirely and still opens the menu', async () => {
    render(
      <SearchableSelect
        value=""
        onChange={vi.fn()}
        options={OPTIONS}
        renderTrigger={({ open }) => (
          <button type="button" data-testid="icon-trigger" aria-expanded={open}>
            +
          </button>
        )}
      />,
    );

    // The default select-box trigger is gone.
    expect(document.querySelector('[data-slot="searchable-select-trigger"]')).toBeNull();

    fireEvent.click(screen.getByTestId('icon-trigger'));
    await waitFor(() => expect(optionLabels()).toHaveLength(3));
  });
});
