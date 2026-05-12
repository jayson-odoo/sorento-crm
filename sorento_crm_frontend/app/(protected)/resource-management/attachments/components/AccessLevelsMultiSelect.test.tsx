import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { AccessLevelsMultiSelect } from './AccessLevelsMultiSelect';

const OPTIONS = [
  { code: 'dealer', name: 'Dealer' },
  { code: 'end_user', name: 'End user' },
  { code: 'sorento_office', name: 'Sorento Office' },
];

function setup(value: string[] = []) {
  const onChange = vi.fn();
  render(<AccessLevelsMultiSelect options={OPTIONS} value={value} onChange={onChange} />);
  return { onChange };
}

describe('AccessLevelsMultiSelect', () => {
  it('shows "Select access levels" placeholder when empty', () => {
    setup([]);
    expect(screen.getByRole('button', { name: /select access levels/i })).toBeInTheDocument();
  });

  it('shows "N selected" with selected count', () => {
    setup(['dealer', 'end_user']);
    expect(screen.getByRole('button', { name: /2 selected/i })).toBeInTheDocument();
  });

  it('renders a removable pill per selected code', () => {
    setup(['dealer', 'sorento_office']);
    expect(screen.getByText('Dealer')).toBeInTheDocument();
    expect(screen.getByText('Sorento Office')).toBeInTheDocument();
  });

  it('clicking a pill remove button calls onChange without that code', () => {
    const { onChange } = setup(['dealer', 'end_user']);
    const dealerPill = screen.getByText('Dealer').closest('span');
    const removeBtn = dealerPill!.querySelector('button');
    fireEvent.click(removeBtn!);
    expect(onChange).toHaveBeenCalledWith(['end_user']);
  });

  it('clicking pill remove button on every selected code emits empty', () => {
    const { onChange } = setup(['dealer']);
    const pill = screen.getByText('Dealer').closest('span');
    fireEvent.click(pill!.querySelector('button')!);
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
