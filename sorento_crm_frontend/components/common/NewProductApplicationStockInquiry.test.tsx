/**
 * NPA-FROM-SI: the NPA "Stock inquiry" tab draws the inquiry status as a Badge.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { NewProductApplicationStockInquiry } from '@/components/common/NewProductApplicationStockInquiry';

const inquiry = {
  id: 'si-1',
  inquiry_number: 'SI26-0412',
  product_code: 'XY-1234-MB',
  status: 'responded',
  item_description: 'Kitchen sink',
  purchasing_response: 'Supplier can do it',
  quantity: '55',
};

describe('NewProductApplicationStockInquiry', () => {
  it('draws the status through the Badge component', () => {
    render(<NewProductApplicationStockInquiry inquiry={inquiry} href={(id) => `/si/${id}`} />);
    const pill = screen.getByText('Responded');
    const badge = pill.closest('[data-slot="badge"]');
    expect(badge).not.toBeNull();
    expect(badge!.textContent).toBe('Responded');
  });

  it('draws no status pill when the inquiry has no status', () => {
    render(<NewProductApplicationStockInquiry inquiry={{ ...inquiry, status: '' }} />);
    expect(document.querySelector('[data-slot="badge"]')).toBeNull();
  });

  it('keeps the empty state heading and hint with no inquiry', () => {
    render(<NewProductApplicationStockInquiry inquiry={null} />);
    expect(screen.getByRole('heading', { name: 'No stock inquiry' })).toBeInTheDocument();
    expect(screen.getByText('Applications raised from a stock inquiry show it here.')).toBeInTheDocument();
  });
});
