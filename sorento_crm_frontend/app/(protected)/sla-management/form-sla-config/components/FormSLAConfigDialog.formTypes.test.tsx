/**
 * QUOTE-DRAWING-ESCALATE rework: the Form type select of the Form SLA stage dialog no longer
 * offers "Product Drawing" (the escalation uses the general-enquiries route, not a stage), and a
 * new stage of any other type gets no team set pre-filled.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

type Option = { value: string; label: string };
const typeSelects: Option[][] = [];

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ options, value }: { options: Option[]; value: string }) => {
    typeSelects.push(options);
    return (
      <ul data-testid="select" data-value={value}>
        {options.map((o) => (
          <li key={o.value}>{o.label}</li>
        ))}
      </ul>
    );
  },
  SearchableMultiSelect: () => null,
}));

vi.mock('../../sla-policies/services/slaPolicyService', () => ({
  getSLAPolicies: vi.fn(async () => ({ data: [], total: 0 })),
}));

import FormSLAConfigDialog from './FormSLAConfigDialog';

describe('FormSLAConfigDialog form types', () => {
  it('offers neither Product Drawing nor Product Photo, and still offers the real form types', () => {
    typeSelects.length = 0;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <FormSLAConfigDialog open existing={null} configs={[]} onClose={() => {}} onSaved={() => {}} />
      </QueryClientProvider>,
    );

    const typeOptions = typeSelects.find((opts) => opts.some((o) => o.value === 'stock_inquiry'));
    expect(typeOptions, 'the Form type select did not render').toBeDefined();
    const values = (typeOptions as Option[]).map((o) => o.value);
    const labels = (typeOptions as Option[]).map((o) => o.label);
    expect(values).not.toContain('product_drawing');
    expect(values).not.toContain('product_photo');
    expect(labels).not.toContain('Product Drawing');
    expect(labels).not.toContain('Product Photo');
    expect(values).toContain('purchase_request');
    expect(screen.queryByText('Product Drawing')).not.toBeInTheDocument();
  });
});
