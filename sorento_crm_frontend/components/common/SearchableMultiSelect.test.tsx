import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

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

describe('SearchableMultiSelect — select all', () => {
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

describe('SearchableMultiSelect — what the menu says is chosen', () => {
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
