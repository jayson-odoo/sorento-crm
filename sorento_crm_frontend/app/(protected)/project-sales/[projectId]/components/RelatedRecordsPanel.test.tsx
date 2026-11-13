/**
 * PROJECT-RELATED-RECORDS red tests: the project's Related tab grid.
 *
 * UAC AC-A3, AC-A4, AC-A6, AC-A7, AC-A9, AC-A10 (documentation/plans/project-sales/
 * project-related-records-12nov-acceptance-criteria.md); contract section 7. The panel reads the
 * rows from `useProjectRelatedRecords(projectId, params)` and the frontend registry; the Type
 * filter offers only the kinds the API's `types` names. Fake values only.
 */
import React from 'react';
import { fireEvent, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { project, renderWithClient, response, ROWS, TYPES } from './relatedRecordsTestKit';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

// A plain stand-in, so the test reads the options each filter offers without driving a popover.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    options,
    value,
    onChange,
    placeholder,
  }: {
    options: { value: string; label: string }[];
    value: string[];
    onChange: (v: string[]) => void;
    placeholder?: string;
  }) => (
    <div data-testid="multi-select" data-placeholder={placeholder ?? ''}>
      {options.map((o) => (
        <button
          type="button"
          key={o.value}
          data-value={o.value}
          onClick={() => onChange([...(value ?? []), o.value])}
        >
          {o.label}
        </button>
      ))}
    </div>
  ),
}));

const state: {
  related: ReturnType<typeof response>;
  rollup: unknown;
  calls: unknown[][];
} = { related: response(), rollup: undefined, calls: [] };

vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useProjectRelatedRecords: (...args: unknown[]) => {
      state.calls.push(args);
      return {
        data: state.related,
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      };
    },
    useSponsorshipRollup: () => ({
      data: state.rollup,
      isLoading: false,
      isError: false,
      error: null,
    }),
  };
});

import { RelatedRecordsPanel } from './RelatedRecordsPanel';

const KINDS = new Set(TYPES.map((t) => t.kind));

/** The Type and Status filters sit in the toolbar's Filters popover (fix round 2, review S1). */
async function openFilters() {
  await userEvent.setup().click(screen.getByRole('button', { name: /^filters/i }));
}

function typeFilter(): HTMLElement {
  const found = screen
    .getAllByTestId('multi-select')
    .find((el) =>
      Array.from(el.querySelectorAll('button')).some((b) =>
        KINDS.has(b.getAttribute('data-value') ?? ''),
      ),
    );
  expect(found, 'a Type multi-select offering record kinds').toBeTruthy();
  return found!;
}

function rowOf(number: string): HTMLElement {
  const cell = screen.getByText(number);
  const row = cell.closest('tr');
  expect(row, `a grid row for ${number}`).toBeTruthy();
  return row as HTMLElement;
}

beforeEach(() => {
  push.mockReset();
  state.related = response();
  state.rollup = { total: '1200.00', form_count: 1, by_year: [{ year: 2026, total: '1200.00' }] };
  state.calls = [];
});

describe('RelatedRecordsPanel', () => {
  it('AC-A4 shows the eight columns', () => {
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
    for (const label of [
      'Type',
      'Number',
      'Status',
      'Approval',
      'Date',
      'Raised by',
      'Subject',
      'Value',
    ]) {
      expect(headers.some((h) => h?.includes(label)), label).toBe(true);
    }
    expect(headers.some((h) => /open/i.test(h ?? '')), 'no Open column').toBe(false);
  });

  it('AC-A3 renders one line per row with the type label, a name and dd/mm/yyyy', () => {
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    expect(state.calls[0]?.[0]).toBe('p1');
    for (const r of ROWS) {
      const row = rowOf(r.number!);
      expect(within(row).getByText(r.raised_by!)).toBeTruthy();
    }
    expect(within(rowOf('SF-ZZT-0001')).getByText('Sponsorship form')).toBeTruthy();
    expect(within(rowOf('NPA-990001')).getByText('New product application')).toBeTruthy();
    expect(within(rowOf('SF-ZZT-0001')).getByText('10/04/2026')).toBeTruthy();
    expect(within(rowOf('SI-ZZT-0001')).getByText('09/01/2026')).toBeTruthy();
  });

  it('AC-A4 shows "-" for a missing approval and value, and RM for a value', () => {
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    const complaint = rowOf('CX-ZZT-0001');
    expect(within(complaint).getAllByText('-').length).toBeGreaterThanOrEqual(2);
    expect(within(rowOf('PR-ZZT-0001')).getByText(/5,000/)).toBeTruthy();
    expect(within(rowOf('PR-ZZT-0001')).getByText(/RM/)).toBeTruthy();
  });

  it.each([
    ['SI-ZZT-0001', '/procurement-management/stock-inquiries/si-1'],
    ['CX-ZZT-0001', '/complaint-management/complaints/cx-1'],
    ['PR-ZZT-0001', '/procurement-management/purchase-requests/pr-1'],
    // A sponsorship form's page names this project as its origin, so its Back returns here
    // (PROJECT-STAGE-ACTIONS, `BackToList originLabel`).
    [
      'SF-ZZT-0001',
      `/procurement-management/sponsorship-forms/sf-1?back=${encodeURIComponent('/project-sales/p1?tab=sponsorships')}`,
    ],
    ['NPA-990001', '/procurement-management/new-product-applications/npa-1'],
  ])('AC-A7 clicking %s opens its own page', (number, href) => {
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    fireEvent.click(screen.getByText(number));
    expect(push).toHaveBeenCalledWith(href);
  });

  it('AC-A9 no rows: heading "No related records", no button', () => {
    state.related = response([]);
    state.rollup = { total: '0', form_count: 0, by_year: [] };
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    expect(screen.getByText('No related records')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /create|add|new/i })).toBeNull();
  });

  it('AC-A7 there is no Create button and no row buttons', () => {
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    expect(screen.queryByRole('button', { name: /create/i })).toBeNull();
    expect(within(rowOf('PR-ZZT-0001')).queryAllByRole('button')).toHaveLength(0);
  });

  it('AC-A6 the Type filter offers only the types the API names', async () => {
    const visible = TYPES.filter((t) => t.kind !== 'complaint');
    state.related = response(
      ROWS.filter((r) => r.kind !== 'complaint'),
      visible,
    );
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    await openFilters();
    const offered = Array.from(typeFilter().querySelectorAll('button')).map((b) => ({
      kind: b.getAttribute('data-value'),
      label: b.textContent,
    }));
    expect(offered).toEqual(visible);
  });

  it('AC-A6 picking a type sends it to the server', async () => {
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    await openFilters();
    const before = state.calls.length;
    fireEvent.click(
      within(typeFilter()).getByText('Complaint', { selector: 'button' }),
    );
    const params = state.calls.slice(before).map((c) => JSON.stringify(c[1] ?? {}));
    expect(params.some((p) => p.includes('complaint'))).toBe(true);
  });

  it('AC-A10 the sponsorship spend line shows when the project has a sponsorship form', () => {
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    expect(screen.getAllByText('2026', { exact: true }).length).toBeGreaterThan(0);
  });

  it('AC-A10 no sponsorship form, no spend line', () => {
    state.related = response(ROWS.filter((r) => r.kind !== 'sponsorship_form'));
    state.rollup = { total: '0', form_count: 0, by_year: [] };
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    expect(screen.queryAllByText('2026', { exact: true })).toHaveLength(0);
    expect(screen.queryByText(/across \d+ form/)).toBeNull();
  });
});
