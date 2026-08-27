/**
 * R18 / AC-F4 - a supplier select on a packing-list screen reads as a factory NAME.
 *
 * The code is ours, the name is what the operator calls the factory, and "(400-K029)" after
 * every entry is noise on a list that is read by name. It stays in `searchText`, so typing a
 * code still finds the supplier.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const captured: { options?: Array<{ value: string; label: string; searchText?: string }> } = {};

// The real SearchableSelect drives a cmdk popover; this test is about the option LABELS the
// wrapper hands it, not about popover mechanics.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    options: Array<{ value: string; label: string; searchText?: string }>;
  }) => {
    captured.options = props.options;
    return (
      <ul data-testid="options">
        {props.options.map((o) => (
          <li key={o.value}>{o.label}</li>
        ))}
      </ul>
    );
  },
}));

import { SupplierCombobox } from './SupplierCombobox';

const SUPPLIERS = [
  { id: 'sup-a', supplier_code: '400-K029', supplier_name: 'KAILU HARDWARE FACTORY' },
  { id: 'sup-b', supplier_code: '400-C011', supplier_name: 'CAIZHOU SANITARY' },
];

describe('SupplierCombobox', () => {
  it('labels each supplier with its name alone', () => {
    render(<SupplierCombobox value="" onChange={vi.fn()} suppliers={SUPPLIERS} />);

    expect(screen.getByText('KAILU HARDWARE FACTORY')).toBeInTheDocument();
    expect(screen.getByText('CAIZHOU SANITARY')).toBeInTheDocument();
    expect(screen.queryByText(/400-K029/)).not.toBeInTheDocument();
    expect(captured.options?.map((o) => o.label)).toEqual([
      'KAILU HARDWARE FACTORY',
      'CAIZHOU SANITARY',
    ]);
  });

  it('keeps the code searchable, so typing one still finds the factory', () => {
    render(<SupplierCombobox value="" onChange={vi.fn()} suppliers={SUPPLIERS} />);

    expect(captured.options?.[0].searchText).toContain('400-K029');
    expect(captured.options?.[0].searchText).toContain('KAILU HARDWARE FACTORY');
  });
});
