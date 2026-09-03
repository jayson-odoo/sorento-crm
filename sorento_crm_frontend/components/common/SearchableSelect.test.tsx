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

// A supplier picker sat on 21 rows literally named "Testing Company" (prod data): cmdk used
// to key each item's identity off `searchText ?? label + description`, so every option sharing
// a label collided on the SAME identity and hovering/arrowing to one highlighted all of them.
// AC: hovering one highlights only that one; picking the second of two duplicates returns its
// own id (S10 fix 1a).
describe('SearchableSelect identity with duplicate labels', () => {
  const DUPES: SearchableSelectOption[] = [
    { value: 'sup-1', label: 'Testing Company' },
    { value: 'sup-2', label: 'Testing Company' },
  ];
  const options = () => [...document.querySelectorAll('[role="option"]')];

  it('highlights only the hovered option among identically labelled ones', async () => {
    render(<SearchableSelect value="" onChange={vi.fn()} options={DUPES} />);
    openMenu();
    await waitFor(() => expect(options()).toHaveLength(2));

    fireEvent.pointerMove(options()[1]);

    await waitFor(() => {
      const [first, second] = options();
      expect(first.getAttribute('aria-selected')).toBe('false');
      expect(second.getAttribute('aria-selected')).toBe('true');
    });
  });

  it('selecting the second of two identically labelled options returns its own id', async () => {
    const onChange = vi.fn();
    render(<SearchableSelect value="" onChange={onChange} options={DUPES} />);
    openMenu();
    await waitFor(() => expect(options()).toHaveLength(2));

    fireEvent.click(options()[1]);

    expect(onChange).toHaveBeenCalledWith('sup-2');
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

// A supplier picker that reads "CHAOZHOU JINBAICHUAN SANITARY WARE TECHNOLO..." does not say
// which supplier the loading plan was built for, and the column it sits in cannot be widened to
// suit the longest name. The label wraps; the trigger grows. AC-A0.1, AC-A0.2, AC-A0.3.
describe('SearchableSelect shows the whole option', () => {
  const LONG = 'CHAOZHOU JINBAICHUAN SANITARY WARE TECHNOLOGY CO., LTD';
  const longOptions: SearchableSelectOption[] = [
    { value: 'jbc', label: LONG, description: 'Guangdong, China - ceramic sanitary ware' },
  ];

  it('never truncates or line-clamps the selected label', () => {
    render(<SearchableSelect value="jbc" onChange={vi.fn()} options={longOptions} />);

    const trigger = document.querySelector('[data-slot="searchable-select-trigger"]')!;
    const label = trigger.querySelector('span')!;
    expect(label.textContent).toBe(LONG);
    expect(label.className).not.toMatch(/\btruncate\b/);
    expect(label.className).toMatch(/\bbreak-words\b/);
    // The clamp used to live on the trigger itself, targeting every direct span child.
    expect(trigger.className).not.toMatch(/line-clamp-1/);
    // A fixed height would clip the second line the wrap creates.
    expect(trigger.className).not.toMatch(/(^|\s)h-\d/);
    expect(trigger.className).toMatch(/min-h-/);
  });

  it('wraps option labels and descriptions without opting in', async () => {
    render(<SearchableSelect value="" onChange={vi.fn()} options={longOptions} />);
    openMenu();

    await waitFor(() => expect(optionLabels()).toHaveLength(1));
    const spans = [...document.querySelectorAll('[role="option"] span')];
    expect(spans.length).toBeGreaterThan(0);
    for (const span of spans) expect(span.className).not.toMatch(/\btruncate\b/);
  });
});
