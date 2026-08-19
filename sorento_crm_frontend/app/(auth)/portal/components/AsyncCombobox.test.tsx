/**
 * AsyncCombobox - the id-valued picker contract (AC-F4's registered-project field).
 *
 * Two things separate that picker from the free-text ones next to it: what it stores is
 * an id rather than the text, and typing something that matched nothing must NOT become
 * the stored value. Free text in a UUID FK column reached Postgres as an id and came back
 * an internal server error, so both halves are pinned here.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { AsyncCombobox } from './AsyncCombobox';

type Project = { id: string; project_code: string; title: string };

const PROJECTS: Project[] = [
  { id: '11111111-1111-1111-1111-111111111111', project_code: 'PRJ-001', title: 'Tower A' },
];

function renderPicker(
  over: Partial<React.ComponentProps<typeof AsyncCombobox<Project>>> = {},
) {
  const onChange = vi.fn();
  render(
    <AsyncCombobox<Project>
      id="project_id"
      value=""
      onChange={onChange}
      fetchOptions={async () => PROJECTS}
      optionValue={(o) => o.id}
      optionLabel={(o) => `${o.project_code} - ${o.title}`}
      allowFreeText={false}
      {...over}
    />,
  );
  return { onChange };
}

describe('AsyncCombobox with allowFreeText={false}', () => {
  it('discards text that matched no option instead of passing it on as a value', async () => {
    const { onChange } = renderPicker();
    const input = screen.getByRole('textbox');

    fireEvent.change(input, { target: { value: 'PO received' } });
    fireEvent.blur(input);

    await waitFor(() => expect((input as HTMLInputElement).value).toBe(''));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('still clears the selection when the box is emptied - that is a deliberate act', async () => {
    const { onChange } = renderPicker({
      value: PROJECTS[0].id,
      displayValue: 'PRJ-001',
    });
    const input = screen.getByRole('textbox');

    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(''));
  });

  it('shows the human label for a saved id, never the id itself', () => {
    renderPicker({ value: PROJECTS[0].id, displayValue: 'PRJ-001' });

    expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('PRJ-001');
  });

  it('stores the id but displays the option label after a pick', async () => {
    const { onChange } = renderPicker();
    const input = screen.getByRole('textbox');

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'PRJ' } });
    const option = await screen.findByText('PRJ-001 - Tower A', {}, { timeout: 2000 });
    fireEvent.mouseDown(option);
    fireEvent.click(option);

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(PROJECTS[0].id, PROJECTS[0]),
    );
    expect((input as HTMLInputElement).value).toBe('PRJ-001 - Tower A');
  });
});
