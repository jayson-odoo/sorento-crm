/**
 * P11 - the revision review.
 *
 * The reviewer has exactly one question, "did anything other than the dates change?", so the
 * headline sentence is asserted for both answers. `unmatched` is asserted in both directions
 * too: a phase that could not be paired up must be shown, and when there is none the section
 * still says so, because a silently empty section is how a delta lies.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  AmendmentDeltaRow,
  AmendmentPreview,
  ProjectSalesOrderDetail,
} from '../../../../../_shared/types/projectSalesOrder.types';

const getProjectSalesOrder = vi.fn();
const previewAmendment = vi.fn();
const createAmendment = vi.fn();
const listScheduleVersions = vi.fn();
const listPoVersions = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1/revisions',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('../../../../../_shared/services/projectSalesOrderService', () => ({
  PROJECT_SO_MOCK: false,
  listProjectSalesOrders: vi.fn(),
  buildSalesOrders: vi.fn(),
  getProjectSalesOrder: (...args: unknown[]) => getProjectSalesOrder(...args),
  acknowledgeFinding: vi.fn(),
  updateSalesOrderLine: vi.fn(),
  regroupSalesOrder: vi.fn(),
  publishSalesOrder: vi.fn(),
  previewAmendment: (...args: unknown[]) => previewAmendment(...args),
  createAmendment: (...args: unknown[]) => createAmendment(...args),
  getAmendment: vi.fn(),
  publishAmendment: vi.fn(),
  listScheduleVersions: (...args: unknown[]) => listScheduleVersions(...args),
  listPoVersions: (...args: unknown[]) => listPoVersions(...args),
}));

vi.mock('../../../../../_shared/hooks/useProjects', () => ({
  useProject: () => ({ data: { id: 'p1', can_edit: true }, isLoading: false, isError: false }),
  usePurchaseOrders: () => ({
    data: [{ id: 'po-1', po_number: 'HQ/26/01/121' }],
    isLoading: false,
    isError: false,
  }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { AmendmentReviewClient } from './AmendmentReviewClient';

function salesOrder(): ProjectSalesOrderDetail {
  return {
    id: 'so-1',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO397450',
    area_group: 'TOWER',
    status: 'published',
    grouping_origin: 'area',
    line_count: 99,
    total_amount: '1611107.81',
    hard_findings: 0,
    warn_findings: 0,
    is_pre_order: false,
    is_sponsorship: false,
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    lines: [],
    findings: [],
  };
}

const DATE_ROWS: AmendmentDeltaRow[] = [
  {
    so_line_id: 'l3',
    line_no: 3,
    product_code: 'SRTWC8613-RL',
    description: 'SORENTO ONE PIECE WASH DOWN (RIMLESS) WC S-TRAP',
    verb: 'DELAY',
    field: 'delivery_date',
    from_value: '2026-07-01',
    to_value: '2027-01-07',
    qty: '135',
    phase_label_from: 'Level 2 & 7',
    phase_label_to: 'Level 2 & 7',
  },
  {
    so_line_id: 'l5',
    line_no: 5,
    product_code: 'SRTWCX8608-RL',
    description: 'SORENTO CLOSE COUPLED PEDESTAL',
    verb: 'DELAY',
    field: 'delivery_date',
    from_value: '2026-08-03',
    to_value: '2027-01-21',
    qty: '124',
    phase_label_from: 'Level 8 & 10',
    phase_label_to: 'Level 8 & 10',
  },
];

function preview(overrides: Partial<AmendmentPreview> = {}): AmendmentPreview {
  return {
    from: { kind: 'schedule_version', id: 'sched-v1', version_no: 1, label: 'R1' },
    to: { kind: 'schedule_version', id: 'sched-v2', version_no: 2, label: 'REVISED 1' },
    verb_summary: { DELAY: 2 },
    rows: DATE_ROWS,
    unmatched: [],
    ...overrides,
  };
}

function renderReview() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AmendmentReviewClient projectId="p1" psoId="so-1" />
    </QueryClientProvider>,
  );
}

async function compare(version = 'schedule:sched-v2') {
  fireEvent.change(await screen.findByLabelText('Select a version'), {
    target: { value: version },
  });
  fireEvent.click(screen.getByRole('button', { name: /Compare/ }));
}

beforeEach(() => {
  vi.clearAllMocks();
  getProjectSalesOrder.mockResolvedValue(salesOrder());
  listScheduleVersions.mockResolvedValue([
    { id: 'sched-v1', version_no: 1, revision_label: 'R1', issuer_party_label: 'Buimaco Sdn Bhd' },
    {
      id: 'sched-v2',
      version_no: 2,
      revision_label: 'REVISED 1 - 23/7/2026',
      issuer_party_label: 'SLG Construction Sdn Bhd',
    },
  ]);
  listPoVersions.mockResolvedValue([
    { id: 'po-v1', version_no: 1, po_number: 'HQ/26/01/121' },
  ]);
});

describe('AmendmentReviewClient', () => {
  it('waits to be asked and writes nothing until then', async () => {
    renderReview();

    expect(await screen.findByText('Nothing compared yet')).toBeInTheDocument();
    expect(previewAmendment).not.toHaveBeenCalled();
  });

  it('reads a date-only revision as date-only', async () => {
    previewAmendment.mockResolvedValue(preview());

    renderReview();
    await compare();

    await waitFor(() =>
      expect(previewAmendment).toHaveBeenCalledWith('so-1', {
        schedule_version_id: 'sched-v2',
      }),
    );

    expect(await screen.findByTestId('delta-headline')).toHaveTextContent(
      'Dates only. 2 lines move; quantities, prices and products are unchanged.',
    );
    expect(screen.getByText('DELAY 2')).toBeInTheDocument();
    // Dates render as dates, in the order everyone here reads them.
    expect(screen.getByText('01/07/2026')).toBeInTheDocument();
    expect(screen.getByText('07/01/2027')).toBeInTheDocument();
  });

  it('says plainly when something other than the dates changed', async () => {
    previewAmendment.mockResolvedValue(
      preview({
        verb_summary: { DELAY: 2, 'CANCEL BALANCE': 1 },
        rows: [
          ...DATE_ROWS,
          {
            so_line_id: 'l1',
            line_no: 1,
            product_code: 'CB6633',
            description: 'CABANA S/STEEL FLOOR GRATING 6"',
            verb: 'CANCEL BALANCE',
            field: 'qty',
            from_value: '600',
            to_value: '570',
            qty: '30',
          },
        ],
      }),
    );

    renderReview();
    await compare();

    expect(await screen.findByTestId('delta-headline')).toHaveTextContent(
      'Not only dates: 1 quantity change, alongside 2 date moves.',
    );
    expect(screen.getByText('CANCEL BALANCE 1')).toBeInTheDocument();
  });

  it('narrows to the changes that are not date moves', async () => {
    previewAmendment.mockResolvedValue(
      preview({
        rows: [
          ...DATE_ROWS,
          {
            so_line_id: 'l1',
            line_no: 1,
            product_code: 'CB6633',
            verb: 'CANCEL BALANCE',
            field: 'qty',
            from_value: '600',
            to_value: '570',
            qty: '30',
          },
        ],
      }),
    );

    renderReview();
    await compare();

    await screen.findByText('CB6633');
    fireEvent.click(screen.getByLabelText('Hide date moves'));

    expect(screen.getByText('CB6633')).toBeInTheDocument();
    expect(screen.queryByText('SRTWC8613-RL')).not.toBeInTheDocument();
  });

  it('shows a phase that could not be matched rather than dropping it', async () => {
    previewAmendment.mockResolvedValue(
      preview({
        unmatched: [
          {
            reason: 'phase not found in the new version',
            detail: 'COMMON AREA row 3 (unlabeled, 08/07/2027) has no counterpart in REVISED 1.',
          },
        ],
      }),
    );

    renderReview();
    await compare();

    expect(await screen.findByText('phase not found in the new version')).toBeInTheDocument();
    expect(
      screen.getByText('COMMON AREA row 3 (unlabeled, 08/07/2027) has no counterpart in REVISED 1.'),
    ).toBeInTheDocument();
    expect(screen.getByText('1 unmatched')).toBeInTheDocument();
    expect(screen.queryByTestId('unmatched-empty')).not.toBeInTheDocument();
  });

  it('states that nothing was unmatched instead of leaving the section out', async () => {
    previewAmendment.mockResolvedValue(preview());

    renderReview();
    await compare();

    expect(await screen.findByTestId('unmatched-empty')).toHaveTextContent(
      'Every phase and product matched across the two versions.',
    );
  });

  it('reports a failed comparison', async () => {
    // Rejected lazily, inside the implementation, so the promise is created when the
    // mutation calls it. mockRejectedValue builds the rejected promise at setup time,
    // and react-query has not attached a handler yet, so it surfaces as an unhandled
    // rejection that vitest reports as possibly making other tests pass falsely.
    previewAmendment.mockImplementation(() =>
      Promise.reject(new Error('The two versions are not comparable')),
    );

    renderReview();
    await compare();

    expect(
      await screen.findByText('The two versions could not be compared'),
    ).toBeInTheDocument();
    expect(screen.getByText('The two versions are not comparable')).toBeInTheDocument();
  });

  it('needs a reason before it writes an amendment, then names the change notice', async () => {
    previewAmendment.mockResolvedValue(preview());
    createAmendment.mockResolvedValue({
      amendment_id: 'am-1',
      ocn_id: 'ocn-1',
      ocn_number: 'OCN-000045',
      verb_summary: { DELAY: 2 },
    });

    renderReview();
    await compare();

    fireEvent.click(await screen.findByRole('button', { name: 'Create the amendment' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Create the amendment' })).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText(/Reason/), {
      target: { value: 'Main contractor pushed every date by twelve months.' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create the amendment' }));

    await waitFor(() =>
      expect(createAmendment).toHaveBeenCalledWith('so-1', {
        schedule_version_id: 'sched-v2',
        reason: 'Main contractor pushed every date by twelve months.',
      }),
    );
    expect(
      await screen.findByText(
        'Change notice OCN-000045 is drafted from this delta. Both wait for review.',
      ),
    ).toBeInTheDocument();
  });
});
