/**
 * N-10 (review round 2, PR #1302) - the opt-in "Add {WORD}" row:
 * - is not offered for a word the list already has (case-insensitive), whether it
 *   is an option or already chosen;
 * - is reachable by keyboard: Enter in the search box adds the typed word, rather
 *   than ticking whichever option happens to be highlighted.
 * A caller without `createOption` is unaffected.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { SearchableMultiSelect } from './SearchableMultiSelect';

const openMenu = () =>
  fireEvent.click(document.querySelector('[data-slot="searchable-multi-select-trigger"]')!);
const createRow = () => document.querySelector('[data-slot="searchable-multi-select-create"]');
const typeQuery = (text: string) =>
  fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: text } });

function renderWithCreate(props: Partial<React.ComponentProps<typeof SearchableMultiSelect>> = {}) {
  const onChange = vi.fn();
  const onCreate = vi.fn();
  render(
    <SearchableMultiSelect
      value={[]}
      onChange={onChange}
      options={[{ value: 'ROUND', label: 'ROUND' }]}
      createOption={{ label: (q) => <span>Add {q.toUpperCase()}</span>, onCreate }}
      {...props}
    />,
  );
  return { onChange, onCreate };
}

describe('N-10 - "Add {WORD}" is not offered for a word already there', () => {
  it('hides it when the typed word matches an option in another case', () => {
    renderWithCreate();
    openMenu();
    typeQuery('round');
    expect(createRow()).toBeNull();
  });

  it('hides it when the typed word is already chosen', () => {
    renderWithCreate({ value: ['OVAL'] });
    openMenu();
    typeQuery('Oval');
    expect(createRow()).toBeNull();
  });

  it('still offers it for a word that is genuinely new', () => {
    renderWithCreate();
    openMenu();
    typeQuery('oval');
    expect(createRow()).not.toBeNull();
    expect(createRow()!.textContent).toContain('Add OVAL');
  });
});

describe('N-10 - "Add {WORD}" is reachable by keyboard', () => {
  it('Enter in the search box adds the typed word, not the highlighted option', () => {
    const { onChange, onCreate } = renderWithCreate({
      options: [{ value: 'OVAL WIDE', label: 'OVAL WIDE' }],
    });
    openMenu();
    typeQuery('oval');
    fireEvent.keyDown(screen.getByPlaceholderText('Search...'), { key: 'Enter' });

    expect(onCreate).toHaveBeenCalledWith('oval');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('a caller without createOption still ticks the highlighted option on Enter', () => {
    const onChange = vi.fn();
    render(
      <SearchableMultiSelect
        value={[]}
        onChange={onChange}
        options={[{ value: 'OVAL WIDE', label: 'OVAL WIDE' }]}
      />,
    );
    openMenu();
    typeQuery('oval');
    fireEvent.keyDown(screen.getByPlaceholderText('Search...'), { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith(['OVAL WIDE']);
  });
});
