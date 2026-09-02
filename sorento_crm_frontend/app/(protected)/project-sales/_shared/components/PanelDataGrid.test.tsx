/**
 * PanelDataGrid: expansion is opt-in.
 *
 * Fifteen existing panels pass no `expanded` prop at all, and the doc comment on
 * `PanelDataGrid` states the contract explicitly: "without it the expanded row model is never
 * built, so fifteen existing panels keep the exact table they have today." A caller wires
 * `expanded` + `onExpandedChange` itself (the way `BoardCellBreakdownDialog` does for the
 * decision panel); a caller that does not gets no expansion at all, whatever it clicks.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ColumnDef, ExpandedState } from '@tanstack/react-table';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { PanelDataGrid } from './PanelDataGrid';

interface Row {
  id: string;
  name: string;
}

const ROWS: Row[] = [{ id: 'r1', name: 'One' }];

function columnsWithExpansion(): ColumnDef<Row>[] {
  return [
    {
      id: 'name',
      accessorFn: (row) => row.name,
      header: 'Name',
      cell: ({ row }) => row.original.name,
      size: 120,
      meta: {
        headerTitle: 'Name',
        expandedContent: (row: Row) => <div data-testid="expanded-panel">{`Detail for ${row.id}`}</div>,
      },
    },
  ];
}

describe('PanelDataGrid: no `expanded` prop, no expansion', () => {
  it('never shows the expanded content, even when a row is clicked', () => {
    const onRowClick = vi.fn();
    render(
      <PanelDataGrid<Row>
        title="Rows"
        columns={columnsWithExpansion()}
        rows={ROWS}
        getRowId={(row) => row.id}
        listingKey="test.panel-data-grid.no-expansion"
        onRowClick={onRowClick}
        emptyTitle="No rows"
      />,
    );

    fireEvent.click(screen.getByText('One'));

    expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);
    expect(screen.queryByTestId('expanded-panel')).not.toBeInTheDocument();
  });
});

describe('PanelDataGrid: `expanded` wired by the caller expands in place', () => {
  function Wrapper() {
    const [expanded, setExpanded] = React.useState<ExpandedState>({});
    return (
      <PanelDataGrid<Row>
        title="Rows"
        columns={columnsWithExpansion()}
        rows={ROWS}
        getRowId={(row) => row.id}
        listingKey="test.panel-data-grid.with-expansion"
        expanded={expanded}
        onExpandedChange={setExpanded}
        onRowClick={(row) =>
          setExpanded((current) =>
            typeof current === 'object' && current[row.id] ? {} : { [row.id]: true },
          )
        }
        emptyTitle="No rows"
      />
    );
  }

  it('renders the expanded content once the caller opts in and toggles it', () => {
    render(<Wrapper />);

    expect(screen.queryByTestId('expanded-panel')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('One'));

    expect(screen.getByTestId('expanded-panel')).toHaveTextContent('Detail for r1');
  });
});

/**
 * D3 (captain, 3 Sep). A panel rendered INSIDE another scrolling table - the fulfilment
 * board's stock drill expands one under every location row - scrolled with only the outer
 * table's header frozen, so the ledger's rows ended up under column headers belonging to a
 * different table ("Quantity" and "Balance after" reading under "Available for Project").
 *
 * `stickyTop` is the offset the caller MEASURES (the outer header's own height, which wraps
 * to two lines at 375px), never a number written down here.
 */
describe('PanelDataGrid: stickyTop pins the header under an outer one', () => {
  function renderGrid(stickyTop?: number) {
    render(
      <PanelDataGrid<Row>
        columns={columnsWithExpansion()}
        rows={ROWS}
        getRowId={(row) => row.id}
        listingKey="test.panel-data-grid.sticky"
        emptyTitle="No rows"
        stickyTop={stickyTop}
      />,
    );
    return screen.getByRole('table').querySelector('thead') as HTMLElement;
  }

  it('sticks its header at the offset it was given', () => {
    const head = renderGrid(96);

    expect(head.style.position).toBe('sticky');
    expect(head.style.top).toBe('96px');
    // Under the outer header, never over it: the two stack, they do not fight.
    expect(Number(head.style.zIndex)).toBeLessThan(10);
  });

  it('leaves the header alone when no offset is given', () => {
    const head = renderGrid();

    expect(head.style.position).toBe('');
    expect(head.style.top).toBe('');
  });
});
