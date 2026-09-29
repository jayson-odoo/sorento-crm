/**
 * Chatbot stock ask v2 S5 review: the customer edit page carries the same line tabs, in
 * the same order, as the view page (view = edit).
 */
import React, { Suspense } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/order-management/customers/cust-1/edit',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock('../../components/CustomerForm', () => ({ default: () => <div>the customer form</div> }));
vi.mock('../../components/CustomerAsksTab', () => ({
  CustomerAsksTab: ({ customerId }: { customerId: string }) => <div>asks of {customerId}</div>,
}));

import EditCustomerPage from './page';

describe('EditCustomerPage - tabs', () => {
  it('shows Details then Asks, like the view page', async () => {
    await act(async () => {
      render(
        <Suspense fallback={null}>
          <EditCustomerPage params={Promise.resolve({ id: 'cust-1' })} />
        </Suspense>,
      );
    });
    const tabs = await screen.findAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['Details', 'Asks']);
    expect(screen.getByText('the customer form')).toBeInTheDocument();
    fireEvent.mouseDown(tabs[1]);
    fireEvent.click(tabs[1]);
    await waitFor(() => expect(screen.getByText('asks of cust-1')).toBeInTheDocument());
  });
});
