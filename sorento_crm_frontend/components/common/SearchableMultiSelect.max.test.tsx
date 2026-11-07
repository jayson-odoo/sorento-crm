/**
 * PRICETAG-COMBO-RENDER K5 / AC-C2: `max` on SearchableMultiSelect.
 *
 * Written test-FIRST. `max` is not a prop yet: Select all still shows and nothing disables.
 * Decision: a row counts as disabled when cmdk marks it `aria-disabled="true"`, and a click
 * on it never calls onChange.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';

import { SearchableMultiSelect, type SearchableMultiSelectOption } from './SearchableMultiSelect';

const OPTIONS: SearchableMultiSelectOption[] = ['a', 'b', 'c', 'd', 'e'].map((v) => ({
  value: v,
  label: `Tap ${v.toUpperCase()}`,
}));

// `max` is typed through a cast so this file compiles before the prop exists.
type Props = React.ComponentProps<typeof SearchableMultiSelect> & { max?: number };
const Multi = SearchableMultiSelect as unknown as React.ComponentType<Props>;

function renderMulti(props: Partial<Props> = {}) {
  const onChange = vi.fn();
  const utils = render(<Multi value={[]} onChange={onChange} options={OPTIONS} {...props} />);
  return { onChange, ...utils };
}

const openMenu = () =>
  fireEvent.click(document.querySelector('[data-slot="searchable-multi-select-trigger"]')!);
const selectAll = () => document.querySelector('[data-slot="searchable-multi-select-all"]');
const rows = () => [...document.querySelectorAll('[role="option"]')] as HTMLElement[];
const rowFor = (label: string) => rows().find((r) => r.textContent?.includes(label))!;
const isDisabled = (el: HTMLElement) =>
  el.getAttribute('aria-disabled') === 'true' || el.getAttribute('data-disabled') === 'true';

beforeEach(() => vi.clearAllMocks());
afterEach(() => cleanup());

describe('SearchableMultiSelect max', () => {
  it('shows no Select all row when max is set', async () => {
    renderMulti({ max: 3 });
    openMenu();
    await waitFor(() => expect(rows()).toHaveLength(5));
    expect(selectAll()).toBeNull();
  });

  it('still shows Select all when max is not set', async () => {
    renderMulti();
    openMenu();
    await waitFor(() => expect(rows()).toHaveLength(5));
    expect(selectAll()).not.toBeNull();
  });

  it('leaves every option enabled while fewer than max are picked', async () => {
    renderMulti({ max: 3, value: ['a', 'b'] });
    openMenu();
    await waitFor(() => expect(rows()).toHaveLength(5));
    expect(rows().filter(isDisabled)).toHaveLength(0);
  });

  it('disables every unselected option once max are picked and keeps the picked ones enabled', async () => {
    renderMulti({ max: 3, value: ['a', 'b', 'c'] });
    openMenu();
    await waitFor(() => expect(rows()).toHaveLength(5));
    expect(isDisabled(rowFor('Tap D'))).toBe(true);
    expect(isDisabled(rowFor('Tap E'))).toBe(true);
    expect(isDisabled(rowFor('Tap A'))).toBe(false);
    expect(isDisabled(rowFor('Tap B'))).toBe(false);
    expect(isDisabled(rowFor('Tap C'))).toBe(false);
  });

  it('does not add a fourth pick when a disabled row is clicked', async () => {
    const { onChange } = renderMulti({ max: 3, value: ['a', 'b', 'c'] });
    openMenu();
    await waitFor(() => expect(rows()).toHaveLength(5));
    fireEvent.click(rowFor('Tap D'));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('deselecting a pick re-enables the rest', async () => {
    const { onChange, rerender } = renderMulti({ max: 3, value: ['a', 'b', 'c'] });
    openMenu();
    await waitFor(() => expect(rows()).toHaveLength(5));

    fireEvent.click(rowFor('Tap B'));
    expect(onChange).toHaveBeenCalledWith(['a', 'c']);

    rerender(<Multi value={['a', 'c']} onChange={onChange} options={OPTIONS} max={3} />);
    await waitFor(() => expect(isDisabled(rowFor('Tap D'))).toBe(false));
    expect(rows().filter(isDisabled)).toHaveLength(0);
  });

  it('keeps picks in pick order as chips', async () => {
    const { onChange } = renderMulti({ max: 3, value: ['c', 'a'] });
    openMenu();
    await waitFor(() => expect(rows()).toHaveLength(5));
    fireEvent.click(rowFor('Tap E'));
    expect(onChange).toHaveBeenCalledWith(['c', 'a', 'e']);
  });
});
