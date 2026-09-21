/**
 * AC-HL-01, browser-pass fix round (`PLAN-oi-header-list-detail.md`): the outer
 * Documents | Lines switch is keyed on `?display=lines`, NEVER on `?view=` - that
 * param already belongs to `OrderInquiriesClient`'s own List | Schedule toggle, and a
 * second control writing it would fight that screen's own URL-sync effect the moment
 * it mounted (see the component's own docstring). `OrderInquiriesClient` and
 * `OrderInquiryHeadersList` are stubbed out - this test is about the SWITCH, not the
 * two screens it chooses between (each has its own test file).
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const routerPush = vi.fn();
let currentSearchParams = new URLSearchParams('');

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: (...args: unknown[]) => routerPush(...args) }),
  usePathname: () => '/project-sales/order-inquiries',
  useSearchParams: () => currentSearchParams,
}));

vi.mock('./OrderInquiriesClient', () => ({
  // The switch hands its OWN toggle to `OrderInquiriesClient` as `extraHeaderActions`
  // (see the component's docstring - it rides in that screen's PageHeader rather than
  // a second one stacked above) - the toggle has to render here for a "Documents"
  // press from the Lines view to have a button to find at all.
  OrderInquiriesClient: ({ extraHeaderActions }: { extraHeaderActions?: React.ReactNode }) => (
    <div data-testid="lines-view">{extraHeaderActions}</div>
  ),
}));
vi.mock('./OrderInquiryHeadersList', () => ({
  OrderInquiryHeadersList: () => <div data-testid="documents-view" />,
}));

import { OrderInquiryHeadersOrLinesView } from './OrderInquiryHeadersOrLinesView';

beforeEach(() => {
  routerPush.mockReset();
  currentSearchParams = new URLSearchParams('');
});

describe('OrderInquiryHeadersOrLinesView toggle (AC-HL-01)', () => {
  it('defaults to Documents when display is unset', () => {
    render(<OrderInquiryHeadersOrLinesView />);
    expect(screen.getByTestId('documents-view')).toBeInTheDocument();
    expect(screen.queryByTestId('lines-view')).not.toBeInTheDocument();
  });

  it('pressing Lines writes ?display=lines and never touches ?view=', () => {
    render(<OrderInquiryHeadersOrLinesView />);
    fireEvent.click(screen.getByRole('button', { name: /lines/i }));

    expect(routerPush).toHaveBeenCalledWith('/project-sales/order-inquiries?display=lines');
    expect(routerPush.mock.calls[0][0]).not.toMatch(/view=/);
  });

  it('reads display=lines back from the URL and renders the Lines worklist', () => {
    currentSearchParams = new URLSearchParams('display=lines');
    render(<OrderInquiryHeadersOrLinesView />);
    expect(screen.getByTestId('lines-view')).toBeInTheDocument();
  });

  it('pressing Documents from Lines clears the param entirely, not to view=list', () => {
    currentSearchParams = new URLSearchParams('display=lines');
    render(<OrderInquiryHeadersOrLinesView />);
    fireEvent.click(screen.getByRole('button', { name: /documents/i }));

    expect(routerPush).toHaveBeenCalledWith('/project-sales/order-inquiries');
  });
});
