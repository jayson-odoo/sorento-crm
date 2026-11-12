/**
 * PRICETAG-MULTI-ADD: SearchableSelect `multiAdd` (AC-1, 2, 4, 5, 6, 7, 8). Written test-FIRST
 * against the Contract in pricetag-multi-add-acceptance-criteria.md.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import { SearchableSelect, type SearchableSelectOption } from './SearchableSelect';

const opt = (code: string, extra: Partial<SearchableSelectOption> = {}): SearchableSelectOption => ({
  value: `product:${code}`,
  label: code,
  code,
  ...extra,
});

const BS = ['DIY-BS-4501', 'DIY-BS-4502', 'DIY-BS-4503'].map((c) => opt(c));
const MR = ['DIY-MR-4601', 'DIY-MR-4602'].map((c) => opt(c));

function makeFetch(all: SearchableSelectOption[] = [...BS, ...MR]) {
  return vi.fn(async (q: string) => {
    const needle = q.trim().toLowerCase();
    return all.filter((o) => o.label.toLowerCase().includes(needle));
  });
}

type MultiAdd = NonNullable<React.ComponentProps<typeof SearchableSelect>['multiAdd']>;

function setup(
  opts: {
    fetchOptions?: ReturnType<typeof makeFetch>;
    isAdded?: MultiAdd['isAdded'];
    capped?: MultiAdd['capped'];
    withMulti?: boolean;
  } = {},
) {
  const onAddMany = vi.fn();
  const onChange = vi.fn();
  const onOptionChange = vi.fn();
  const fetchOptions = opts.fetchOptions ?? makeFetch();
  const props: React.ComponentProps<typeof SearchableSelect> = {
    value: '',
    onChange,
    onOptionChange,
    fetchOptions,
    placeholder: 'Search a set or product...',
    ...(opts.withMulti === false
      ? {}
      : { multiAdd: { onAddMany, isAdded: opts.isAdded, capped: opts.capped } }),
  };
  render(<SearchableSelect {...props} />);
  return { onAddMany, onChange, onOptionChange, fetchOptions };
}

const openMenu = async () => {
  fireEvent.click(screen.getByRole('combobox'));
  await screen.findByPlaceholderText('Search...');
};
const input = () => screen.getByPlaceholderText('Search...');
const search = (text: string) => fireEvent.change(input(), { target: { value: text } });
const tick = (label: string) => screen.getByRole('checkbox', { name: `Tick ${label}` });
const listOpen = () => screen.queryByPlaceholderText('Search...') !== null;

beforeEach(() => vi.clearAllMocks());
afterEach(() => cleanup());

describe('multiAdd AC-1 tick and stay open', () => {
  it('ticking keeps the list open, the search text, and shows "1 ticked" + "Add 1"', async () => {
    setup();
    await openMenu();
    search('DIY');
    await screen.findByRole('checkbox', { name: 'Tick DIY-BS-4501' });
    expect(screen.queryByText(/ticked/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Add \d+$/ })).not.toBeInTheDocument();

    fireEvent.click(tick('DIY-BS-4501'));

    expect(tick('DIY-BS-4501')).toHaveAttribute('aria-checked', 'true');
    expect(listOpen()).toBe(true);
    expect((input() as HTMLInputElement).value).toBe('DIY');
    expect(screen.getByText('1 ticked')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add 1' })).toBeInTheDocument();
  });

  it('without multiAdd no tick boxes render', async () => {
    setup({ withMulti: false });
    await openMenu();
    await screen.findByText('DIY-BS-4501');
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });
});

describe('multiAdd AC-2 single pick unchanged', () => {
  it('clicking the option text calls onOptionChange and closes', async () => {
    const { onOptionChange, onAddMany } = setup();
    await openMenu();
    fireEvent.click(await screen.findByText('DIY-BS-4502'));
    expect(onOptionChange).toHaveBeenCalledWith(expect.objectContaining({ value: 'product:DIY-BS-4502' }));
    expect(onAddMany).not.toHaveBeenCalled();
    await waitFor(() => expect(listOpen()).toBe(false));
  });
});

describe('multiAdd AC-4 already added', () => {
  const isAdded = (o: SearchableSelectOption) => o.value === 'product:DIY-BS-4502';

  it('shows a disabled ticked box with the "Already added" hint', async () => {
    setup({ isAdded });
    await openMenu();
    const box = await screen.findByRole('checkbox', { name: 'Tick DIY-BS-4502' });
    expect(box).toHaveAttribute('aria-checked', 'true');
    expect(box).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText('Already added')).toBeInTheDocument();
  });

  it('cannot be ticked, and Select all skips it', async () => {
    const { onAddMany } = setup({ isAdded });
    await openMenu();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Tick DIY-BS-4502' }));
    expect(screen.queryByText(/ticked/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Select all 4'));
    expect(screen.getByText('4 ticked')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add 4' }));
    expect(onAddMany).toHaveBeenCalledTimes(1);
    expect(onAddMany.mock.calls[0][0].map((o: SearchableSelectOption) => o.label)).not.toContain(
      'DIY-BS-4502',
    );
  });
});

describe('multiAdd AC-5 select all', () => {
  it('ticks every shown result, and a second click unticks them', async () => {
    setup();
    await openMenu();
    await screen.findByText('DIY-BS-4501');
    fireEvent.click(screen.getByText('Select all 5'));
    expect(screen.getByText('5 ticked')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Select all 5'));
    expect(screen.queryByText(/ticked/)).not.toBeInTheDocument();
  });

  it('reads "Select all N shown" plus the cap line when capped', async () => {
    setup({ capped: () => true });
    await openMenu();
    await screen.findByText('DIY-BS-4501');
    expect(screen.getByText('Select all 5 shown')).toBeInTheDocument();
    expect(screen.getByText('More match. Type more of the code to see them.')).toBeInTheDocument();
  });

  it('shows no cap line when not capped', async () => {
    setup({ capped: () => false });
    await openMenu();
    await screen.findByText('DIY-BS-4501');
    expect(screen.queryByText('More match. Type more of the code to see them.')).not.toBeInTheDocument();
  });
});

describe('multiAdd AC-6 ticks across searches', () => {
  it('keeps earlier ticks when the search changes; footer shows the total; Add N sends both in tick order', async () => {
    const { onAddMany } = setup();
    await openMenu();
    search('DIY-BS');
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Tick DIY-BS-4501' }));
    search('DIY-MR');
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Tick DIY-MR-4602' }));
    expect(screen.getByText('2 ticked')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Add 2' }));
    expect(onAddMany).toHaveBeenCalledTimes(1);
    expect(onAddMany.mock.calls[0][0].map((o: SearchableSelectOption) => o.label)).toEqual([
      'DIY-BS-4501',
      'DIY-MR-4602',
    ]);
    await waitFor(() => expect(listOpen()).toBe(false));
  });
});

describe('multiAdd AC-7 Escape drops the ticks', () => {
  it('closes, calls nothing, and reopens with no ticks', async () => {
    const { onAddMany, onOptionChange } = setup();
    await openMenu();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Tick DIY-BS-4501' }));
    fireEvent.keyDown(input(), { key: 'Escape' });
    await waitFor(() => expect(listOpen()).toBe(false));
    expect(onAddMany).not.toHaveBeenCalled();
    expect(onOptionChange).not.toHaveBeenCalled();

    await openMenu();
    await screen.findByRole('checkbox', { name: 'Tick DIY-BS-4501' });
    expect(tick('DIY-BS-4501')).toHaveAttribute('aria-checked', 'false');
    expect(screen.queryByText(/ticked/)).not.toBeInTheDocument();
  });
});

describe('multiAdd AC-8 keyboard', () => {
  it('ArrowDown then Space ticks the highlighted result and leaves the search text', async () => {
    setup();
    await openMenu();
    await screen.findByText('DIY-BS-4501');
    search('DIY-BS');
    await waitFor(() => expect(screen.queryByText('DIY-MR-4601')).not.toBeInTheDocument());
    fireEvent.keyDown(input(), { key: 'ArrowDown' });
    const notPrevented = fireEvent.keyDown(input(), { key: ' ' });
    expect(notPrevented).toBe(false);
    expect(screen.getByText('1 ticked')).toBeInTheDocument();
    expect((input() as HTMLInputElement).value).toBe('DIY-BS');
    expect(listOpen()).toBe(true);
  });

  it('typing then Space types a space instead of ticking', async () => {
    setup();
    await openMenu();
    await screen.findByText('DIY-BS-4501');
    search('basin');
    const notPrevented = fireEvent.keyDown(input(), { key: ' ' });
    expect(notPrevented).toBe(true);
    expect(screen.queryByText(/ticked/)).not.toBeInTheDocument();
  });

  it('Ctrl+Enter calls onAddMany with the ticked options', async () => {
    const { onAddMany, onOptionChange } = setup();
    await openMenu();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Tick DIY-BS-4503' }));
    fireEvent.keyDown(input(), { key: 'Enter', ctrlKey: true });
    expect(onAddMany).toHaveBeenCalledTimes(1);
    expect(onAddMany.mock.calls[0][0].map((o: SearchableSelectOption) => o.label)).toEqual(['DIY-BS-4503']);
    expect(onOptionChange).not.toHaveBeenCalled();
  });

  it('Enter alone is still a single pick', async () => {
    const { onOptionChange, onAddMany } = setup();
    await openMenu();
    await screen.findByText('DIY-BS-4501');
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(onOptionChange).toHaveBeenCalledTimes(1);
    expect(onAddMany).not.toHaveBeenCalled();
  });
});

describe('multiAdd Add N', () => {
  it('calls onAddMany once with the ticked options and closes', async () => {
    const { onAddMany } = setup();
    await openMenu();
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Tick DIY-BS-4501' }));
    fireEvent.click(tick('DIY-BS-4503'));
    const footerBtn = screen.getByRole('button', { name: 'Add 2' });
    expect(within(footerBtn).queryByRole('checkbox')).toBeNull();
    fireEvent.click(footerBtn);
    expect(onAddMany).toHaveBeenCalledTimes(1);
    expect(onAddMany.mock.calls[0][0].map((o: SearchableSelectOption) => o.value)).toEqual([
      'product:DIY-BS-4501',
      'product:DIY-BS-4503',
    ]);
    await waitFor(() => expect(listOpen()).toBe(false));
  });
});
