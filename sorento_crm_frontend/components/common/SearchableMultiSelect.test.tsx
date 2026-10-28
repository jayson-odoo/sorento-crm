import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';

import { SearchableMultiSelect, type SearchableMultiSelectOption } from './SearchableMultiSelect';

const OPTIONS: SearchableMultiSelectOption[] = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta' },
  { value: 'c', label: 'Gamma' },
];

/** Renders the component as a controlled input so assertions see committed state. */
function renderMulti(props: Partial<React.ComponentProps<typeof SearchableMultiSelect>> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <SearchableMultiSelect value={[]} onChange={onChange} options={OPTIONS} {...props} />,
  );
  return { onChange, ...utils };
}

// The trigger renders chips once values are selected, so it has no stable accessible name.
const openMenu = () =>
  fireEvent.click(document.querySelector('[data-slot="searchable-multi-select-trigger"]')!);
const selectAllButton = () => document.querySelector('[data-slot="searchable-multi-select-all"]')!;

beforeEach(() => vi.clearAllMocks());

describe('SearchableMultiSelect - select all', () => {
  it('offers select all with the option count and selects every value', async () => {
    const { onChange } = renderMulti();
    openMenu();

    await waitFor(() => expect(selectAllButton()).toBeTruthy());
    expect(selectAllButton().textContent).toContain('Select all (3)');

    fireEvent.click(selectAllButton());
    expect(onChange).toHaveBeenCalledWith(['a', 'b', 'c']);
  });

  it('clears all when everything is already selected', async () => {
    const { onChange } = renderMulti({ value: ['a', 'b', 'c'] });
    openMenu();

    await waitFor(() => expect(selectAllButton().textContent).toContain('Clear all'));
    fireEvent.click(selectAllButton());
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('acts only on rows matching the active search, leaving filtered-out selections alone', async () => {
    const { onChange } = renderMulti({ value: ['a'] });
    openMenu();

    fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: 'et' } });

    // Only "Beta" matches, so select-all must not sweep in Alpha/Gamma.
    await waitFor(() => expect(selectAllButton().textContent).toContain('Select 1 matching'));
    fireEvent.click(selectAllButton());
    expect(onChange).toHaveBeenCalledWith(['a', 'b']);
  });

  it('clearing while filtered keeps selections that are filtered out', async () => {
    const { onChange } = renderMulti({ value: ['a', 'b'] });
    openMenu();

    fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: 'beta' } });

    await waitFor(() => expect(selectAllButton().textContent).toContain('Clear 1 matching'));
    fireEvent.click(selectAllButton());
    // Alpha survives: it was never visible.
    expect(onChange).toHaveBeenCalledWith(['a']);
  });

  it('never selects a disabled option', async () => {
    const { onChange } = renderMulti({
      options: [...OPTIONS, { value: 'd', label: 'Delta', disabled: true }],
    });
    openMenu();

    await waitFor(() => expect(selectAllButton().textContent).toContain('Select all (3)'));
    fireEvent.click(selectAllButton());
    expect(onChange).toHaveBeenCalledWith(['a', 'b', 'c']);
  });

  it('labels async mode as loaded-only, since the full server set is unknown', async () => {
    const fetchOptions = vi.fn().mockResolvedValue([OPTIONS[0], OPTIONS[1]]);
    renderMulti({ options: undefined, fetchOptions });
    openMenu();

    await waitFor(() => expect(selectAllButton().textContent).toContain('Select all 2 loaded'));
  });

  it('hides the control when there is nothing selectable', async () => {
    renderMulti({ options: [] });
    openMenu();

    await waitFor(() => expect(screen.getByText('No results found.')).toBeTruthy());
    expect(selectAllButton()).toBeNull();
  });
});

// Same standard as SearchableSelect (S10 fix 1a): filtering here is manual (`visibleOptions`,
// `shouldFilter={false}`), and `CommandItem`'s `value` was already `opt.value` (unique by
// construction) rather than `searchText ?? label + description`, so this component never had
// the identity collision - but it is pinned here so a future edit that copies the wrong pattern
// from elsewhere trips a test, not a prod incident with duplicate labels.
describe('SearchableMultiSelect identity with duplicate labels', () => {
  const DUPES: SearchableMultiSelectOption[] = [
    { value: 'sup-1', label: 'Testing Company' },
    { value: 'sup-2', label: 'Testing Company' },
  ];
  const options = () => [...document.querySelectorAll('[role="option"]')];

  it('highlights only the hovered option among identically labelled ones', async () => {
    render(<SearchableMultiSelect value={[]} onChange={vi.fn()} options={DUPES} />);
    openMenu();
    await waitFor(() => expect(options()).toHaveLength(2));

    fireEvent.pointerMove(options()[1]);

    await waitFor(() => {
      const [first, second] = options();
      expect(first.getAttribute('aria-selected')).toBe('false');
      expect(second.getAttribute('aria-selected')).toBe('true');
    });
  });

  it('toggling the second of two identically labelled options returns its own id', async () => {
    const onChange = vi.fn();
    render(<SearchableMultiSelect value={[]} onChange={onChange} options={DUPES} />);
    openMenu();
    await waitFor(() => expect(options()).toHaveLength(2));

    fireEvent.click(options()[1]);

    expect(onChange).toHaveBeenCalledWith(['sup-2']);
  });

  it('toggling one of two identically labelled options keeps the other already-selected id', async () => {
    const onChange = vi.fn();
    render(<SearchableMultiSelect value={['sup-1']} onChange={onChange} options={DUPES} />);
    openMenu();
    await waitFor(() => expect(options()).toHaveLength(2));

    fireEvent.click(options()[1]);

    expect(onChange).toHaveBeenCalledWith(['sup-1', 'sup-2']);
  });
});

/**
 * A controlled parent, which is how every caller uses this: the value it hands
 * back is the value the next click is computed against.
 */
function Controlled({
  initial = [],
  onChange,
}: {
  initial?: string[];
  onChange: (value: string[]) => void;
}) {
  const [value, setValue] = React.useState<string[]>(initial);
  return (
    <SearchableMultiSelect
      value={value}
      options={OPTIONS}
      onChange={(next) => {
        onChange(next);
        setValue(next);
      }}
    />
  );
}

const option = (name: string) => screen.getByRole('option', { name });

describe('SearchableMultiSelect - what the menu says is chosen', () => {
  it('reports every chosen option as chosen, not only the last one clicked', async () => {
    // The bug this pins: the ONLY sign that an option was chosen was a bare tick
    // icon with no text. Nothing reading the page rather than looking at it - a
    // screen reader, or a browser agent working off the accessibility tree -
    // could tell a chosen row from an unchosen one. What it could see was cmdk's
    // own `aria-selected`, which marks the KEYBOARD-HIGHLIGHTED row and follows
    // the pointer, so each click appeared to move "selected" off the previous
    // option: a working multi-select read as a single select.
    const onChange = vi.fn();
    render(<Controlled initial={['a']} onChange={onChange} />);
    openMenu();

    await waitFor(() => expect(option('Alpha')).toBeTruthy());
    expect(option('Alpha')).toHaveAttribute('aria-checked', 'true');
    expect(option('Beta')).toHaveAttribute('aria-checked', 'false');
    expect(option('Gamma')).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(option('Beta'));
    expect(onChange).toHaveBeenLastCalledWith(['a', 'b']);
    // Alpha is still chosen even though the highlight has moved to Beta.
    expect(option('Alpha')).toHaveAttribute('aria-checked', 'true');
    expect(option('Beta')).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(option('Gamma'));
    expect(onChange).toHaveBeenLastCalledWith(['a', 'b', 'c']);
    expect(option('Alpha')).toHaveAttribute('aria-checked', 'true');
    expect(option('Beta')).toHaveAttribute('aria-checked', 'true');
    expect(option('Gamma')).toHaveAttribute('aria-checked', 'true');

    // And clicking a chosen option unchooses that one alone.
    fireEvent.click(option('Alpha'));
    expect(onChange).toHaveBeenLastCalledWith(['b', 'c']);
    expect(option('Alpha')).toHaveAttribute('aria-checked', 'false');
    expect(option('Beta')).toHaveAttribute('aria-checked', 'true');
    expect(option('Gamma')).toHaveAttribute('aria-checked', 'true');
  });

  it('says the list takes more than one answer', async () => {
    renderMulti({ value: ['a'] });
    openMenu();
    await waitFor(() => expect(screen.getByRole('listbox')).toBeTruthy());
    expect(screen.getByRole('listbox')).toHaveAttribute('aria-multiselectable', 'true');
  });
});

// Same standard as SearchableSelect: a chosen option must be readable in full.
// AC-A0.1, AC-A0.2, AC-A0.3.
describe('SearchableMultiSelect shows the whole option', () => {
  const LONG = 'CHAOZHOU JINBAICHUAN SANITARY WARE TECHNOLOGY CO., LTD';
  const longOptions: SearchableMultiSelectOption[] = [
    { value: 'jbc', label: LONG, description: 'Guangdong, China' },
  ];

  it('never truncates the chip label', () => {
    render(
      <SearchableMultiSelect value={['jbc']} onChange={vi.fn()} options={longOptions} />,
    );

    const trigger = document.querySelector('[data-slot="searchable-multi-select-trigger"]')!;
    const chipLabel = [...trigger.querySelectorAll('span')].find(
      (s) => s.textContent === LONG,
    )!;
    expect(chipLabel).toBeTruthy();
    expect(chipLabel.className).not.toMatch(/\btruncate\b/);
    expect(trigger.className).not.toMatch(/line-clamp-1/);
  });

  it('wraps option labels and descriptions without opting in', async () => {
    render(<SearchableMultiSelect value={[]} onChange={vi.fn()} options={longOptions} />);
    openMenu();

    await waitFor(() => expect(document.querySelectorAll('[role="option"]')).toHaveLength(1));
    const spans = [...document.querySelectorAll('[role="option"] span')];
    expect(spans.length).toBeGreaterThan(0);
    for (const span of spans) expect(span.className).not.toMatch(/\btruncate\b/);
  });
});

// Bug: a `renderTrigger` caller (e.g. Notify roles/users on the System Health page) left
// `document.body[data-scroll-locked]` set with nothing open, because the scroll lock was
// wired to "does this popover ever need the wrap", not "is it open right now".
describe('SearchableMultiSelect scroll lock only while open (renderTrigger)', () => {
  afterEach(() => {
    cleanup();
    document.body.removeAttribute('data-scroll-locked');
  });

  const renderWithCustomTrigger = () =>
    render(
      <SearchableMultiSelect
        value={[]}
        onChange={vi.fn()}
        options={OPTIONS}
        renderTrigger={({ open }) => (
          <button type="button" data-testid="custom-trigger">
            {open ? 'Open' : 'Closed'}
          </button>
        )}
      />,
    );

  it('does not lock the page scroll before the popover is opened', () => {
    renderWithCustomTrigger();
    expect(document.body.hasAttribute('data-scroll-locked')).toBe(false);
  });

  it('locks while the popover is open and releases it on Escape', async () => {
    renderWithCustomTrigger();
    fireEvent.click(screen.getByTestId('custom-trigger'));

    await waitFor(() =>
      expect(document.body.hasAttribute('data-scroll-locked')).toBe(true),
    );

    const content = document.querySelector('[data-slot="popover-content"]')!;
    fireEvent.keyDown(content, { key: 'Escape' });

    await waitFor(() =>
      expect(document.body.hasAttribute('data-scroll-locked')).toBe(false),
    );
  });
});

describe('SearchableMultiSelect async pagination', () => {
  const page = (n: number, size: number) =>
    Array.from({ length: size }, (_, i) => ({ value: `p${n}-${i}`, label: `Item ${n}-${i}` }));
  const rows = () => [...document.querySelectorAll('[role="option"]')];
  const labels = () => rows().map((r) => r.textContent?.trim());
  const loadMore = () =>
    document.querySelector('[data-slot="searchable-multi-select-load-more"]') as HTMLElement | null;

  /** A controlled wrapper, so picks made on page 1 are still in `value` after page 2 arrives. */
  function Controlled({ fetchOptions, onValue }: { fetchOptions: (q: string, p: number) => Promise<SearchableMultiSelectOption[]>; onValue: (v: string[]) => void }) {
    const [value, setValue] = React.useState<string[]>([]);
    return (
      <SearchableMultiSelect
        value={value}
        onChange={(v) => {
          setValue(v);
          onValue(v);
        }}
        fetchOptions={fetchOptions}
        paginated
        pageSize={2}
      />
    );
  }

  afterEach(() => cleanup());

  it('Load more appends the next page, asks for pageIndex 1, and keeps picks across pages', async () => {
    const fetchOptions = vi
      .fn()
      .mockImplementationOnce(async () => page(0, 2))
      .mockImplementationOnce(async () => page(1, 2))
      .mockImplementation(async () => []);
    const onValue = vi.fn();
    render(<Controlled fetchOptions={fetchOptions} onValue={onValue} />);
    openMenu();

    await waitFor(() => expect(rows()).toHaveLength(2));
    fireEvent.click(rows()[0]);
    expect(onValue).toHaveBeenLastCalledWith(['p0-0']);

    fireEvent.click(loadMore()!);

    await waitFor(() => expect(rows()).toHaveLength(4));
    expect(fetchOptions).toHaveBeenNthCalledWith(2, '', 1);
    expect(loadMore()).toBeTruthy(); // a full page means there may be more
    expect(labels()).toEqual(expect.arrayContaining(['Item 0-0', 'Item 0-1', 'Item 1-0', 'Item 1-1']));

    fireEvent.click(rows().find((r) => r.textContent?.includes('Item 1-1'))!);
    expect(onValue).toHaveBeenLastCalledWith(['p0-0', 'p1-1']);
  });

  it('offers no Load more once a page comes back short', async () => {
    const fetchOptions = vi
      .fn()
      .mockImplementationOnce(async () => page(0, 2))
      .mockImplementationOnce(async () => page(1, 1));
    render(<Controlled fetchOptions={fetchOptions} onValue={vi.fn()} />);
    openMenu();

    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(loadMore()).toBeTruthy();
    fireEvent.click(loadMore()!);

    await waitFor(() => expect(rows()).toHaveLength(3));
    await waitFor(() => expect(loadMore()).toBeNull());
  });

  it('offers no Load more when pagination is off', async () => {
    const fetchOptions = vi.fn().mockResolvedValue(page(0, 50));
    render(<SearchableMultiSelect value={[]} onChange={vi.fn()} fetchOptions={fetchOptions} />);
    openMenu();

    await waitFor(() => expect(rows().length).toBeGreaterThan(0));
    expect(loadMore()).toBeNull();
  });

  it('a query change while a page is loading discards that stale page', async () => {
    let releasePage1: (items: SearchableMultiSelectOption[]) => void = () => {};
    const fetchOptions = vi.fn(async (q: string, p: number) => {
      if (q === 'zz') return [{ value: 'zz-0', label: 'Fresh zz' }];
      if (p === 0) return page(0, 2);
      return new Promise<SearchableMultiSelectOption[]>((resolve) => {
        releasePage1 = resolve;
      });
    });
    render(<Controlled fetchOptions={fetchOptions} onValue={vi.fn()} />);
    openMenu();

    await waitFor(() => expect(rows()).toHaveLength(2));
    fireEvent.click(loadMore()!);
    await waitFor(() => expect(fetchOptions).toHaveBeenCalledWith('', 1));

    fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: 'zz' } });
    await waitFor(() => expect(labels()).toEqual(['Fresh zz']));

    releasePage1(page(1, 2));
    await new Promise((r) => setTimeout(r, 50));

    expect(labels()).toEqual(['Fresh zz']);
  });
});
