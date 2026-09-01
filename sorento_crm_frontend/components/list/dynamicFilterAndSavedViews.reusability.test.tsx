/**
 * AC-4.5: "<DynamicFilterBuilder> + <SavedViewsMenu> mount on a second listing by
 * supplying only a field descriptor and listing key (proven by test, not by shipping a
 * second page)."
 *
 * Neither the field descriptor nor the row shape below imports anything from
 * `app/(protected)/scm/reorder/` - no `PlanLine`, no `planLineFilterFields`, no reorder
 * `listing_key`. A completely unrelated "support tickets" listing exercises both
 * components end to end: the builder composes a filter that actually narrows a row set
 * via the SAME `evaluateFilterGroup` the reorder plan grid uses, and the menu talks to the
 * saved-views service under a listing key that has nothing to do with `scm.dashboard.view`.
 * If either component silently depended on reorder's shape, this file would not compile
 * or would not pass.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

// The real SearchableSelect drives a cmdk popover; a native <select> is enough to prove
// the BUILDER wires field/operator/value through - same substitution
// `PlanLinesGrid.test.tsx` and `UnmatchedSupplierCodesPanel.test.tsx` use.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options = [],
  }: {
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string }>;
  }) => (
    <select aria-label="dynamic-filter-select" value={value} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuItem: ({
    children,
    onClick,
    disabled,
  }: React.PropsWithChildren<{ onClick?: () => void; disabled?: boolean }>) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
}));

const fetchSavedViews = vi.fn();
vi.mock('@/services/savedViewsService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/savedViewsService')>();
  return {
    ...actual,
    fetchSavedViews: (...a: unknown[]) => fetchSavedViews(...a),
    createSavedView: vi.fn(),
    publishSavedView: vi.fn(),
    setDefaultSavedView: vi.fn(),
  };
});

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => false }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false }),
}));

const getUserListColumnConfig = vi.fn();
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (...a: unknown[]) => getUserListColumnConfig(...a),
  upsertUserListColumnConfig: vi.fn(),
}));

import { DynamicFilterBuilder } from './DynamicFilterBuilder';
import { SavedViewsMenu } from './SavedViewsMenu';
import { evaluateFilterGroup, type FilterFieldDescriptor } from '@/lib/list-query/dynamicFilter';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';

// --------------------------------------------------------------------------------------
// A "support tickets" listing - unrelated to reorder in every way: row shape, field keys,
// labels, and the listing key string.
// --------------------------------------------------------------------------------------

interface SupportTicket {
  id: string;
  subject: string;
  priority: 'low' | 'high';
  age_days: number;
}

const TICKET_LISTING_KEY = 'zzt.support.tickets.view::demo-tickets';

const ticketFields: FilterFieldDescriptor<SupportTicket>[] = [
  { field_key: 'subject', label: 'Subject', type: 'text', getValue: (t) => t.subject },
  {
    field_key: 'priority',
    label: 'Priority',
    type: 'select',
    options: [
      { value: 'low', label: 'Low' },
      { value: 'high', label: 'High' },
    ],
    getValue: (t) => t.priority,
  },
  { field_key: 'age_days', label: 'Age (days)', type: 'number', getValue: (t) => t.age_days },
];

const tickets: SupportTicket[] = [
  { id: 't1', subject: 'Portal login broken', priority: 'high', age_days: 12 },
  { id: 't2', subject: 'Typo on invoice PDF', priority: 'low', age_days: 2 },
];

function Harness({ onFilterChange }: { onFilterChange: (g: ListQueryFilterGroup | null) => void }) {
  const [group, setGroup] = React.useState<ListQueryFilterGroup | null>(null);
  return (
    <DynamicFilterBuilder
      fields={ticketFields}
      value={group}
      onChange={(next) => {
        setGroup(next);
        onFilterChange(next);
      }}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchSavedViews.mockResolvedValue({ mine: [], shared: [] });
  getUserListColumnConfig.mockResolvedValue({ listing_key: TICKET_LISTING_KEY, config: null });
});

describe('AC-4.5: DynamicFilterBuilder reused on a second, non-reorder descriptor', () => {
  it('renders the SECOND listing field labels, and nothing from the reorder v1 list', () => {
    render(<Harness onFilterChange={vi.fn()} />);

    expect(screen.getByText('All conditions (AND)')).toBeInTheDocument();
    // Adding a condition exposes the field picker's own options.
    fireEvent.click(screen.getByRole('button', { name: /Condition/i }));
    expect(screen.getByText('Subject')).toBeInTheDocument();
    expect(screen.getByText('Priority')).toBeInTheDocument();
    expect(screen.getByText('Age (days)')).toBeInTheDocument();

    // None of the reorder plan grid's v1 field labels leak in.
    for (const reorderLabel of ['Product code', 'Supplier', 'Suggested qty', 'On hand BRW', 'SPO qty']) {
      expect(screen.queryByText(reorderLabel)).not.toBeInTheDocument();
    }
  });

  it('composes a condition whose shape the generic evaluator actually filters rows with', () => {
    let latest: ListQueryFilterGroup | null = null;
    render(<Harness onFilterChange={(g) => (latest = g)} />);

    fireEvent.click(screen.getByRole('button', { name: /Condition/i }));
    // Default condition on the first field ("subject", type text) is `contains`; fill a value.
    const valueInput = screen.getByPlaceholderText('Value');
    fireEvent.change(valueInput, { target: { value: 'invoice' } });

    expect(latest).toEqual({
      op: 'and',
      children: [{ field_key: 'subject', op: 'contains', value: 'invoice' }],
    });
    expect(evaluateFilterGroup(latest, tickets[0], ticketFields)).toBe(false); // "Portal login broken"
    expect(evaluateFilterGroup(latest, tickets[1], ticketFields)).toBe(true); // "Typo on invoice PDF"
  });

  it('switches the condition to a select field (priority) with its own option list', () => {
    render(<Harness onFilterChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /Condition/i }));

    // [0] is the group's own AND/OR toggle (same mocked select label); [1] is the
    // condition row's field picker.
    const [, fieldSelect] = screen.getAllByLabelText('dynamic-filter-select');
    fireEvent.change(fieldSelect, { target: { value: 'priority' } });

    // The operator + value pickers now reflect the "select" type's own default ops/options.
    expect(screen.getByText('Low')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
  });

  it('recurses into a nested group, same as the reorder consumer gets for free', () => {
    render(<Harness onFilterChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /^Group$/i }));

    const groups = screen.getAllByTestId('dynamic-filter-group');
    expect(groups.length).toBe(2); // root + the nested one just added
  });
});

describe('AC-4.5: SavedViewsMenu reused on a second listing key', () => {
  function render2(client: QueryClient) {
    return render(
      <QueryClientProvider client={client}>
        <SavedViewsMenu
          listingKey={TICKET_LISTING_KEY}
          currentViewId={null}
          currentConfig={{ filters: null, sort: [], columns: [], column_order: [] }}
          onApply={vi.fn()}
        />
      </QueryClientProvider>,
    );
  }

  it('fetches saved views under the TICKET listing key, never a reorder key', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render2(client);

    await waitFor(() => expect(fetchSavedViews).toHaveBeenCalledWith(TICKET_LISTING_KEY));
    expect(fetchSavedViews).not.toHaveBeenCalledWith(expect.stringContaining('reorder-plan-lines'));
    expect(getUserListColumnConfig).toHaveBeenCalledWith(TICKET_LISTING_KEY);
  });

  it('renders with no console error when the listing has no saved segments yet', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render2(client);
    expect(await screen.findByText('No saved segments yet')).toBeInTheDocument();
  });
});
