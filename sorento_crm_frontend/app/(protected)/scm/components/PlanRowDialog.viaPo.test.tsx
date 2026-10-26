/**
 * LINKAGE-UNIFY U4 round 2 (P1): the SPO document's "SO covered" lightbox row for a placement
 * that arrived through its PO line. The SO number never truncates; "via PO <number>" is the
 * shared `WorklistPill` (the app Badge) that truncates with the full text in its title -
 * the same rule as the U3 document pills (owner, #1870 round 8).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
Element.prototype.setPointerCapture = Element.prototype.setPointerCapture ?? (() => {});
Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/loading-plan',
}));

const useContainerRequestDrill = vi.fn();
vi.mock('../hooks/useContainerRequestDrill', () => ({
  useContainerRequestDrill: (...a: unknown[]) => useContainerRequestDrill(...a),
}));

const useLocationStock = vi.fn();
vi.mock('../reorder/hooks/useReorderRun', () => ({
  useLocationStock: (...a: unknown[]) => useLocationStock(...a),
}));

vi.mock('../../project-sales/fulfilment-planning/components/StockDocumentsPanel', () => ({
  // Addressed by ids: the panel no longer takes a code at all, since the heading block that
  // printed one was removed (captain, 30 August 2026).
  StockDocumentsPanel: ({ warehouseId }: { warehouseId: string }) => (
    <div data-testid="stock-documents">{`documents for ${warehouseId}`}</div>
  ),
}));

/**
 * The pickers' Filters popover nests a `SearchableSelect` (the field, then the value) inside
 * a Radix `DropdownMenu` - real Radix-in-Radix works in the browser, but jsdom has no repo
 * precedent driving a portalled Popover from inside a portalled DropdownMenu, and the users
 * list's own "Advanced filters" test (`PipelineClient.test.tsx`) sidesteps exactly this by
 * standing in a native `<select>`. Same stand-in here, distinguished by `placeholder`: only
 * the VALUE select gets one ("Any"), so the field select reads "Filter field" and the value
 * select reads "Filter value".
 */
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    clearable,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    clearable?: boolean;
  }) => (
    <select
      aria-label={placeholder ? 'Filter value' : 'Filter field'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      {clearable ? <option value="">{placeholder ?? ''}</option> : null}
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { SoCoveragePicker } from './PlanRowDialog';

const ROW = {
  key: 'project:1',
  kind: 'project' as const,
  demand_class: 'project' as const,
  document: 'SO396349',
  customer_name: 'PEMBINAAN MAJU',
  required_date: '2026-09-30',
  qty: 294,
  warehouse_code: 'BRW',
  taken_qty: 0,
  taken_by: [],
  via_po: '202607-S0100',
};

function show() {
  renderWithClient(
    <SoCoveragePicker coverage={[ROW]} tickedKeys={[]} onChange={() => {}} unassigned={0} />,
  );
}

describe('P1 the via-PO row of the SO covered lightbox', () => {
  it('seed: the row prints the SO number and the via PO mark', () => {
    show();
    expect(screen.getByText('SO396349')).toBeTruthy();
    expect(screen.getByText('via PO 202607-S0100')).toBeTruthy();
  });

  it('the SO number never truncates', () => {
    show();
    const number = screen.getByText('SO396349');
    expect(number.className).toContain('shrink-0');
    expect(number.className).not.toMatch(/truncate|overflow-hidden|text-ellipsis/);
  });

  it('"via PO <number>" is the shared Badge pill, never truncating, full text as title, cell wraps', () => {
    show();
    const text = screen.getByText('via PO 202607-S0100');
    const badge = text.closest('[data-slot="badge"]') as HTMLElement | null;
    expect(badge).not.toBeNull();
    for (const el of [text, badge!]) {
      expect(el.className).not.toMatch(/truncate|overflow-hidden|text-ellipsis/);
    }
    expect(`${text.className} ${badge!.className}`).toContain('whitespace-nowrap');
    expect(badge!.className).toContain('shrink-0');
    expect((text.closest('[title]') as HTMLElement).getAttribute('title')).toBe(
      'via PO 202607-S0100',
    );
    // The cell container wraps so the pill drops under the SO number instead of being cut.
    const cell = screen.getByText('SO396349').parentElement as HTMLElement;
    expect(cell.className).toContain('flex-wrap');
  });
});
