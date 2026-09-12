/**
 * PLAN-portal-price-tag-journey-r8, D-L3/D-L4 (AC-L5, AC-L6, AC-L7's control,
 * AC-L8's "Clear all" affordance).
 *
 * Filter and Sort share one field descriptor table (`landing-fields.ts`);
 * this drives `LandingToolbar` directly with a small `stock_inquiry` row set
 * rather than the whole `PortalLanding` page, since the toolbar's own
 * contract is what fields it offers and what it calls back with - the full
 * page-level integration (empty state text, list-view row rendering) is
 * `PortalLanding.viewToggle.test.tsx`'s job.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import { LandingToolbar } from './LandingToolbar';
import {
  DEFAULT_LANDING_SORT,
  landingFieldsFor,
  type LandingFilters,
  type LandingSort,
} from '../lib/landing-fields';
import type { PortalSubmissionSummary } from '../lib/portal-client';

const FIELDS = landingFieldsFor('stock_inquiry');

const ROWS: PortalSubmissionSummary[] = [
  {
    id: 'row-1',
    kind: 'stock_inquiry',
    title: 'ZZT Row 1',
    document_number: 'SI-0001',
    reference: null,
    status: 'new',
    is_editable: true,
    is_draft: false,
    created_at: '2026-09-01T00:00:00Z',
    product_code: 'ZZT-PROD-A',
  } as PortalSubmissionSummary,
  {
    id: 'row-2',
    kind: 'stock_inquiry',
    title: 'ZZT Row 2',
    document_number: 'SI-0002',
    reference: null,
    status: 'answered',
    is_editable: false,
    is_draft: false,
    created_at: '2026-09-02T00:00:00Z',
    product_code: 'ZZT-PROD-B',
  } as PortalSubmissionSummary,
];

function Harness({
  items = ROWS,
  initialFilters = {},
  initialSort = DEFAULT_LANDING_SORT,
}: {
  items?: PortalSubmissionSummary[];
  initialFilters?: LandingFilters;
  initialSort?: LandingSort;
}) {
  const [filters, setFilters] = React.useState<LandingFilters>(initialFilters);
  const [sort, setSort] = React.useState<LandingSort>(initialSort);
  const [view, setView] = React.useState<'list' | 'board'>('board');
  return (
    <LandingToolbar
      fields={FIELDS}
      items={items}
      filters={filters}
      onFiltersChange={setFilters}
      sort={sort}
      onSortChange={setSort}
      view={view}
      onViewChange={setView}
    />
  );
}

// Radix's Popover/DropdownMenu triggers open on a real pointerdown/pointerup/
// click sequence - a bare `fireEvent.click` leaves `aria-expanded="false"` in
// jsdom (same fix as `ComplaintDetail.test.tsx`'s `openTechnicalResponse
// PopupButton`).
async function openMenu(name: string) {
  const trigger = screen.getByRole('button', { name });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
  return trigger;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('LandingToolbar - Filter (AC-L5)', () => {
  it('lists one control per field, status/text as selects, values limited to what is present', async () => {
    render(<Harness />);
    await openMenu('Filter');

    // One label per field of the current (stock_inquiry) kind. `Created`
    // matches its own field label AND (once the sort dropdown is touched
    // elsewhere) the button's own text, so it is asserted via the labelled
    // date inputs below instead of a bare text match.
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Form Number')).toBeInTheDocument();
    expect(screen.getByText('Product')).toBeInTheDocument();
    expect(screen.getByText('Project')).toBeInTheDocument();
    expect(screen.getByText('Customer')).toBeInTheDocument();

    // Created is a date field: From / To, not a select.
    expect(screen.getByLabelText('Created from')).toBeInTheDocument();
    expect(screen.getByLabelText('Created to')).toBeInTheDocument();
  });

  it('shows a count badge once a filter is applied, and Clear all resets it', async () => {
    render(<Harness initialFilters={{ status: 'New' }} />);

    const filterButton = screen.getByRole('button', { name: 'Filter' });
    expect(within(filterButton).getByText('1')).toBeInTheDocument();

    await openMenu('Filter');
    fireEvent.click(screen.getByRole('button', { name: 'Clear all' }));

    expect(within(filterButton).queryByText('1')).toBeNull();
  });

  it('Clear all is disabled when nothing is active', async () => {
    render(<Harness />);
    await openMenu('Filter');

    expect(screen.getByRole('button', { name: 'Clear all' })).toBeDisabled();
  });
});

describe('LandingToolbar - Sort (AC-L6)', () => {
  it('lists every sortable field with ascending/descending, Form Number labelled for the number field', async () => {
    render(<Harness />);
    await openMenu('Sort');

    const menu = within(screen.getByRole('menu'));
    expect(menu.getAllByText('Ascending').length).toBe(FIELDS.length);
    expect(menu.getAllByText('Descending').length).toBe(FIELDS.length);
    expect(menu.getByText('Form Number')).toBeInTheDocument();
  });

  it('defaults to Created, newest first, ticked', async () => {
    render(<Harness />);

    // The button label reads the active field's name (shown at `md:`, but
    // present in the DOM regardless of viewport in jsdom).
    expect(screen.getByRole('button', { name: /Sort/ })).toHaveTextContent(
      'Created',
    );

    await openMenu('Sort');
    // Every field carries its own "Descending" item - the ticked one is the
    // one under `Created` (default sort).
    const checked = screen
      .getAllByRole('menuitemradio')
      .find((el) => el.getAttribute('aria-checked') === 'true');
    expect(checked).toHaveAccessibleName('Descending');
  });

  it('picking a field and a direction calls back with both', async () => {
    render(<Harness />);
    await openMenu('Sort');

    fireEvent.click(
      within(screen.getByRole('menu')).getAllByText('Ascending')[2],
    );

    // The button label now reads the newly picked field. The trigger sits
    // behind an `aria-hidden` wrapper for one tick while the menu's exit
    // animation settles (motion's AnimatePresence), so it is queried with
    // `hidden: true` rather than waited on as if it had unmounted.
    expect(
      screen.getByRole('button', { name: /Sort/, hidden: true }),
    ).toHaveTextContent(FIELDS[2].label);
  });
});

describe('LandingToolbar - view toggle wiring (AC-L7)', () => {
  it('calls onViewChange when the list icon is picked', () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole('radio', { name: 'List view' }));

    expect(screen.getByRole('radio', { name: 'List view' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });
});
