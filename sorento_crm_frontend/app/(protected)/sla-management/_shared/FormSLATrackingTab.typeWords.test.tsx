/**
 * NPA-FORM-SLA browser pass: the tab named the record "new product_application" (only the first
 * underscore was replaced). It reads the type's own label now, for every form type.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('./formSLAService', async (orig) => ({
  ...(await orig<typeof import('./formSLAService')>()),
  getFormSLATrackers: vi.fn(async () => []),
}));

import FormSLATrackingTab from './FormSLATrackingTab';

function renderTab(type: 'new_product_application' | 'price_tag_request' | 'stock_inquiry') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FormSLATrackingTab sourceEntityType={type} sourceEntityId="r-1" />
    </QueryClientProvider>,
  );
}

describe('FormSLATrackingTab names the record by its type label', () => {
  it('says "new product application", every underscore gone', async () => {
    renderTab('new_product_application');
    expect(await screen.findByText(/attached to this new product application\./)).toBeInTheDocument();
  });

  it('says "price tag request" and keeps "stock inquiry" as before', async () => {
    renderTab('price_tag_request');
    expect(await screen.findByText(/attached to this price tag request\./)).toBeInTheDocument();
  });

  it('keeps the stock inquiry wording', async () => {
    renderTab('stock_inquiry');
    expect(await screen.findByText(/attached to this stock inquiry\./)).toBeInTheDocument();
  });
});
