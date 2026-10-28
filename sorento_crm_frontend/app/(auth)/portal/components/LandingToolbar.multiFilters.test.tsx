/**
 * FILTER-MULTISELECT PR6: the portal landing's list filters (Product, State) take several values (OR); the rows
 * kept are those matching any picked value, one value still works, clearing restores every row.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { LandingToolbar } from './LandingToolbar';
import {
  DEFAULT_LANDING_SORT,
  applyLandingFilters,
  landingFieldValue,
  landingFieldsFor,
  type LandingFilters,
} from '../lib/landing-fields';
import type { PortalSubmissionSummary } from '../lib/portal-client';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});


const FIELDS = landingFieldsFor('stock_inquiry');

function row(id: string, status: string, product: string): PortalSubmissionSummary {
  return {
    id, kind: 'stock_inquiry', title: `ZZT ${id}`, document_number: `SI-${id}`, reference: null, status,
    is_editable: false, is_draft: false, created_at: '2026-09-01T00:00:00Z', product_code: product,
  } as PortalSubmissionSummary;
}
const STATUS_FIELD = FIELDS.find((f) => f.key === 'status')!;
const ROWS = [row('r1', 'new', 'ZZT-PROD-A'), row('r2', 'answered', 'ZZT-PROD-B'), row('r3', 'closed', 'ZZT-PROD-C')];

function Harness() {
  const [filters, setFilters] = React.useState<LandingFilters>({});
  const kept = applyLandingFilters(ROWS, FIELDS, filters)
    .map((r) => r.id)
    .sort()
    .join(',');
  return (
    <>
      <div data-testid="kept">{kept}</div>
      <LandingToolbar
        fields={FIELDS}
        items={ROWS}
        filters={filters}
        onFiltersChange={setFilters}
        sort={DEFAULT_LANDING_SORT}
        onSortChange={() => {}}
        view="board"
        onViewChange={() => {}}
      />
    </>
  );
}

const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}
function openFilter() {
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Filter' }), { button: 0, ctrlKey: false });
  fireEvent.click(screen.getByRole('button', { name: 'Filter' }));
}
const kept = () => screen.getByTestId('kept').textContent;

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

describe('Portal landing - multi filters', () => {
  it('Product is a multi control', async () => {
    render(<Harness />);
    openFilter();
    expect((await box('ZZT-PROD-A')).hasAttribute('multiple')).toBe(true);
  });

  it('two products keep the rows of either', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    openFilter();
    await user.selectOptions(await box('ZZT-PROD-A'), ['ZZT-PROD-A', 'ZZT-PROD-C']);
    await waitFor(() => expect(kept()).toBe('r1,r3'));
  });

  it('two states keep the rows of either', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    openFilter();
    const labels = [ROWS[1], ROWS[2]].map((r) => landingFieldValue(r, STATUS_FIELD) as string);
    expect(new Set(labels).size).toBe(2);
    await user.selectOptions(await box(labels[0]), labels);
    await waitFor(() => expect(kept()).toBe('r2,r3'));
  });

  it('unpicking everything restores every row', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    openFilter();
    await user.selectOptions(await box('ZZT-PROD-A'), ['ZZT-PROD-A', 'ZZT-PROD-C']);
    await waitFor(() => expect(kept()).toBe('r1,r3'));
    await user.deselectOptions(await box('ZZT-PROD-A'), ['ZZT-PROD-A', 'ZZT-PROD-C']);
    await waitFor(() => expect(kept()).toBe('r1,r2,r3'));
  });
});
