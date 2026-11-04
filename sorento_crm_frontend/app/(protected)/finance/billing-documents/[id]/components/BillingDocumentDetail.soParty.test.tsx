/**
 * OI-UX-FILTER-SNAPSHOT: a billing line that comes from a sales order names that order's
 * customer and project under the SO number.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/finance/billing-documents/b-1',
}));

import { LineFrom } from './BillingDocumentDetail';
import type { BillingDocumentLine } from '../../types/billingDocument.types';

const line = (extra: Partial<BillingDocumentLine>) =>
  ({ from_doc_type: 'SO', from_doc_no: 'SO427775', sales_order: null, ...extra }) as BillingDocumentLine;

describe('BillingDocumentDetail LineFrom', () => {
  it('prints CUSTOMER / project under an SO source', () => {
    render(
      <LineFrom
        line={line({
          sales_order: {
            id: 'so-1',
            doc_no: 'SO427775',
            customer_name: 'Maju Debtor',
            project_label: 'Tower B',
          },
        })}
        doIds={new Map()}
      />,
    );
    expect(screen.getByRole('link', { name: 'SO SO427775' })).toBeInTheDocument();
    expect(screen.getByText('Maju Debtor / Tower B')).toBeInTheDocument();
  });

  it('prints it under a DO source that also resolved an SO', () => {
    render(
      <LineFrom
        line={line({
          from_doc_type: 'DO',
          from_doc_no: 'DO-77',
          sales_order: { id: 'so-1', doc_no: 'SO427775', customer_name: 'Maju Debtor', project_label: null },
        })}
        doIds={new Map()}
      />,
    );
    expect(screen.getByText('Maju Debtor / -')).toBeInTheDocument();
  });

  it('prints nothing extra when the order names neither', () => {
    render(<LineFrom line={line({ sales_order: { id: 'so-1', doc_no: 'SO427775' } })} doIds={new Map()} />);
    expect(screen.queryByText(/\//)).toBeNull();
  });
});
