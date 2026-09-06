/**
 * PR / SF edit form: display suffixed, submit bare (UAC N1 against N2).
 *
 * `request_number` is user-assignable and this form posts it back, so the
 * derived `-R{n}` must never enter the form state - it would be written into
 * the very column it was derived from, and every lookup-by-number (the external
 * API's create-or-resubmit key among them, N6) would then miss the row and
 * insert a duplicate. The backend carries a `_strip_number_suffix_in_place`
 * defence; that is a reason to be safe if we get it wrong, not a reason to send
 * it wrong.
 *
 * So: what the user READS carries the revision, what the form SUBMITS does not.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { useForm } from 'react-hook-form';

import { Form } from '@/components/ui/form';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/purchase-requests/pr-1',
}));

vi.mock('@/hooks/useCurrencyFormat', () => ({
  useCurrencyFormat: () => 'RM {value}',
}));
vi.mock('@/components/common/LookupBoundField', () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock(
  '@/app/(protected)/master-data-management/shared/components/RequestorContactSelect',
  () => ({ RequestorContactSelect: () => null }),
);
vi.mock('./PurchaseRequestSignoffFooter', () => ({
  PurchaseRequestSignoffFooter: () => null,
}));

import { PurchaseRequestDocumentEditCard } from './PurchaseRequestDocumentEditCard';
import type { PurchaseRequestSchemaType } from '../forms/purchase-request-schema';
import type { PurchaseRequest } from '../types/purchaseRequest.types';

const BARE = 'PR26-0332';

function request(over: Partial<PurchaseRequest> = {}): PurchaseRequest {
  return {
    id: 'pr-1',
    request_type: 'purchase_request',
    request_number: BARE,
    revision_no: 0,
    lines: [],
    ...over,
  } as PurchaseRequest;
}

/** Renders the card the way the edit page does: bound to the BARE number. */
function Harness({
  record,
  onValues,
}: {
  record: PurchaseRequest;
  onValues: (v: PurchaseRequestSchemaType) => void;
}) {
  const form = useForm<PurchaseRequestSchemaType>({
    defaultValues: {
      request_type: 'purchase_request',
      request_number: record.request_number ?? null,
      products: [],
    } as unknown as PurchaseRequestSchemaType,
  });
  onValues(form.getValues());
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(() => {})}>
        <PurchaseRequestDocumentEditCard
          form={form}
          request={record}
          isSponsorship={record.request_type === 'sponsorship_form'}
          showTypeSelect={false}
          fields={[]}
          append={vi.fn()}
          remove={vi.fn()}
          sponsorshipLineGrandTotal={0}
        />
      </form>
    </Form>
  );
}

function renderCard(record: PurchaseRequest) {
  const seen: PurchaseRequestSchemaType[] = [];
  render(<Harness record={record} onValues={(v) => seen.push(v)} />);
  return { latestValues: () => seen.at(-1)! };
}

function numberInput(): HTMLInputElement {
  return screen.getByPlaceholderText('e.g. PR26-0303') as HTMLInputElement;
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('PR document edit card - the number it shows against the number it posts', () => {
  it('shows the revision suffix while the submitted value stays bare', () => {
    const { latestValues } = renderCard(request({ revision_no: 2 }));
    expect(numberInput().value).toBe('PR26-0332-R2');
    expect(latestValues().request_number).toBe(BARE);
  });

  it('shows the bare number at revision 0 - there is no -R0', () => {
    const { latestValues } = renderCard(request({ revision_no: 0 }));
    expect(numberInput().value).toBe(BARE);
    expect(latestValues().request_number).toBe(BARE);
  });

  it('does the same on a sponsorship form', () => {
    const { latestValues } = renderCard(
      request({ request_type: 'sponsorship_form', request_number: 'PSSF26-0326', revision_no: 4 }),
    );
    expect(numberInput().value).toBe('PSSF26-0326-R4');
    expect(latestValues().request_number).toBe('PSSF26-0326');
  });

  it('keeps the field read-only, so the painted suffix can never be typed into state', () => {
    renderCard(request({ revision_no: 3 }));
    expect(numberInput()).toHaveAttribute('readonly');
  });
});
