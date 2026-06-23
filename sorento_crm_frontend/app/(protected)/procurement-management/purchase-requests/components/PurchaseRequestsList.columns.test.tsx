import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// Render DataGridColumnHeader as a plain element exposing its title so we can
// assert which header the variable column produces, without the full DataGrid.
vi.mock('@/components/ui/data-grid-column-header', () => ({
  DataGridColumnHeader: ({ title }: { title: string }) => <span>{title}</span>,
}));
// LookupBoundLabel pulls a react-query hook; stub it to its raw value.
vi.mock('@/components/common/LookupBoundLabel', () => ({
  default: ({ value }: { value: string }) => <span>{value}</span>,
}));

import { purposeOrSponsorSubjectColumn } from './PurchaseRequestsList';
import type { PurchaseRequest } from '../types/purchaseRequest.types';

function renderHeader(column: ReturnType<typeof purposeOrSponsorSubjectColumn>) {
  const headerFn = column.header as (ctx: { column: unknown }) => React.ReactElement;
  render(headerFn({ column: {} }));
}

function renderCell(
  column: ReturnType<typeof purposeOrSponsorSubjectColumn>,
  row: Partial<PurchaseRequest>,
) {
  const cellFn = column.cell as (ctx: { row: { original: Partial<PurchaseRequest> } }) => React.ReactNode;
  render(<div>{cellFn({ row: { original: row } })}</div>);
}

describe('purposeOrSponsorSubjectColumn', () => {
  it('uses a Sponsor Subject column for sponsorship forms', () => {
    const col = purposeOrSponsorSubjectColumn('sponsorship_form');
    expect((col as { accessorKey?: string }).accessorKey).toBe('sponsor_subject');
    renderHeader(col);
    expect(screen.getByText('Sponsor Subject')).toBeInTheDocument();
  });

  it('renders the sponsor subject value plus the Others detail', () => {
    const col = purposeOrSponsorSubjectColumn('sponsorship_form');
    renderCell(col, { sponsor_subject: 'others', sponsor_subject_other: 'VIP booth' });
    expect(screen.getByText(/others/)).toBeInTheDocument();
    expect(screen.getByText(/: VIP booth/)).toBeInTheDocument();
  });

  it('uses a Purpose column for purchase requests', () => {
    const col = purposeOrSponsorSubjectColumn('purchase_request');
    expect((col as { accessorKey?: string }).accessorKey).toBe('purpose');
    renderHeader(col);
    expect(screen.getByText('Purpose')).toBeInTheDocument();
  });

  it('defaults to Purpose for the combined (unfiltered) list', () => {
    const col = purposeOrSponsorSubjectColumn(undefined);
    expect((col as { accessorKey?: string }).accessorKey).toBe('purpose');
    renderHeader(col);
    expect(screen.getByText('Purpose')).toBeInTheDocument();
  });
});
