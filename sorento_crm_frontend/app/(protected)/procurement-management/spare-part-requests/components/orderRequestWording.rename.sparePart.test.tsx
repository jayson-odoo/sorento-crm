/**
 * SPARE-PART-ORDER-REQUEST owner rename (13 Nov), red-first (Phase 2). F4.
 * "Order Requests" on the list page, "New Order Request" on the create page, "Order request" as
 * the Order Inquiry type label / filter option, "Order Request" as the Form SLA form type.
 * Internal keys stay (inquiry_type value, routes, slugs) and are not asserted here.
 */
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title, actions }: { title: string; actions?: React.ReactNode }) => (
    <header>
      <h1>{title}</h1>
      {actions}
    </header>
  ),
}));
vi.mock('@/components/common/BackToList', () => ({
  default: ({ label }: { label: string }) => <a href="/x">{label}</a>,
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/app/components/common/RequireAccess', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('./SparePartRequestsList', () => ({ SparePartRequestsList: () => <div>list</div> }));
vi.mock(
  '@/app/(protected)/project-sales/order-inquiries/spare-part-requests/components/SparePartRequestForm',
  () => ({ SparePartRequestForm: () => <div>form</div> }),
);

import ListPage, { metadata as listMetadata } from '../page';
import NewPage, { metadata as newMetadata } from '../new/page';
import {
  INQUIRY_TYPE_LABEL,
  INQUIRY_TYPE_OPTIONS,
  inquiryTypeLabel,
} from '@/app/(protected)/project-sales/_shared/lib/sparePartRequest';
import { FORM_SLA_TYPE_LABELS } from '@/app/(protected)/sla-management/_shared/formSLAService';
import { HANDLING_LOCK_TYPE_LABELS } from '@/app/(protected)/sla-management/_shared/handlingLock';

afterEach(cleanup);

describe('F4: page titles', () => {
  it('the list page is titled "Order Requests"', () => {
    render(<ListPage />);
    expect(screen.getByRole('heading', { name: 'Order Requests' })).toBeInTheDocument();
    expect(listMetadata.title).toBe('Order Requests');
  });

  it('the create page is titled "New Order Request" and links back to order requests', () => {
    render(<NewPage />);
    expect(screen.getByRole('heading', { name: 'New Order Request' })).toBeInTheDocument();
    expect(newMetadata.title).toBe('New Order Request');
    expect(screen.getByText(/back to order requests/i)).toBeInTheDocument();
  });
});

describe('F4: the type label and the Form SLA form type', () => {
  it('the Order Inquiry type label reads "Order request"', () => {
    expect(INQUIRY_TYPE_LABEL.spare_part_request).toBe('Order request');
    expect(inquiryTypeLabel({ inquiry_type: 'spare_part_request' })).toBe('Order request');
  });

  it('the type filter option reads "Order request" and keeps its value', () => {
    expect(INQUIRY_TYPE_OPTIONS).toContainEqual({ value: 'spare_part_request', label: 'Order request' });
  });

  it('the Form SLA form type reads "Order Request"', () => {
    expect(FORM_SLA_TYPE_LABELS.spare_part_request).toBe('Order Request');
    expect(HANDLING_LOCK_TYPE_LABELS.spare_part_request).toBe('Order Request');
  });
});
