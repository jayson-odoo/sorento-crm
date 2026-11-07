/**
 * NPA-FROM-SI: the "New product applications" list of a stock inquiry keeps its columns and its
 * empty state (staff and portal share it).
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  InquiryApplicationsList,
  type InquiryApplicationRow,
} from '@/components/common/NewProductApplicationBanners';

const row = (over: Partial<InquiryApplicationRow> = {}): InquiryApplicationRow => ({
  id: 'a-1',
  application_no: 'NPA-000001',
  status: 'completed',
  status_label: 'Completed',
  created_at: '2026-11-03T02:00:00',
  created_codes: [
    { product_code: 'XY-1-69', current_codes: ['XY-1'], created_at: '2026-11-03T02:00:00' },
  ],
  ...over,
});

describe('InquiryApplicationsList', () => {
  it('shows the empty state heading and hint with no rows', () => {
    render(<InquiryApplicationsList applications={[]} renderNumber={(a) => a.application_no} />);
    expect(screen.getByRole('heading', { name: 'No new product applications' })).toBeInTheDocument();
    expect(screen.getByText('Applications created from this inquiry show here.')).toBeInTheDocument();
    expect(screen.queryAllByRole('columnheader')).toHaveLength(0);
  });

  it('keeps the columns Application, Status, New code, Date', () => {
    render(<InquiryApplicationsList applications={[row()]} renderNumber={(a) => a.application_no} />);
    expect(
      screen.getAllByRole('columnheader').map((h) => (h.textContent ?? '').trim()),
    ).toEqual(['Application', 'Status', 'New code', 'Date']);
    expect(screen.getByText('NPA-000001')).toBeInTheDocument();
    expect(screen.getByText('XY-1 -> XY-1-69')).toBeInTheDocument();
    expect(screen.getByText('03/11/2026')).toBeInTheDocument();
  });

  it('shows a dash for the new code of an application that created none', () => {
    render(
      <InquiryApplicationsList
        applications={[row({ status: 'submitted', status_label: 'Submitted', created_codes: [] })]}
        renderNumber={(a) => a.application_no}
      />,
    );
    expect(screen.getByText('Submitted')).toBeInTheDocument();
    expect(screen.getByText('-')).toBeInTheDocument();
  });
});
