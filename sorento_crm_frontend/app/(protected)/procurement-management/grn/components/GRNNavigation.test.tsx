import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// --- mock next/navigation -------------------------------------------------- //
const pushMock = vi.fn();
let searchParamsString = '';
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => new URLSearchParams(searchParamsString),
}));

// --- mock the neighbours hook (thin wrapper around useRecordNeighbours) ---- //
import type { RecordNeighboursResult } from '@/hooks/useRecordNeighbours';

const neighboursMock = vi.fn<() => RecordNeighboursResult>();
vi.mock('../hooks/useGRN', () => ({
  useGRNNeighbours: () => neighboursMock(),
}));

import GRNNavigation from './GRNNavigation';

function setNeighbours(partial: Partial<RecordNeighboursResult>) {
  neighboursMock.mockReturnValue({
    prevId: null,
    nextId: null,
    index: null,
    total: 0,
    isLoading: false,
    ...partial,
  });
}

beforeEach(() => {
  pushMock.mockReset();
  neighboursMock.mockReset();
  searchParamsString = '';
});

describe('GRNNavigation (IDs mode)', () => {
  it('renders the 1-based "index / total" counter from the hook', () => {
    setNeighbours({ prevId: 'a', nextId: 'c', index: 2, total: 5 });
    render(<GRNNavigation grnId="b" />);
    expect(screen.getByText('2 / 5')).toBeInTheDocument();
  });

  it('enables both chevrons when total > 1 (circular wrap)', () => {
    setNeighbours({ prevId: 'a', nextId: 'c', index: 2, total: 5 });
    render(<GRNNavigation grnId="b" />);
    expect(
      screen.getByRole('button', { name: /previous grn/i }),
    ).toBeEnabled();
    expect(screen.getByRole('button', { name: /next grn/i })).toBeEnabled();
  });

  it('disables both chevrons when total <= 1', () => {
    setNeighbours({ prevId: null, nextId: null, index: 1, total: 1 });
    render(<GRNNavigation grnId="only" />);
    expect(
      screen.getByRole('button', { name: /previous grn/i }),
    ).toBeDisabled();
    expect(screen.getByRole('button', { name: /next grn/i })).toBeDisabled();
  });

  it('shows a loading counter while neighbours resolve', () => {
    setNeighbours({ total: 5, isLoading: true });
    render(<GRNNavigation grnId="b" />);
    expect(screen.getByText('… / 5')).toBeInTheDocument();
  });

  it('navigates to next neighbour preserving the active list query', () => {
    searchParamsString = 'query=SPO-1&sort=picking_date&dir=desc&picking_status=approved';
    setNeighbours({ prevId: 'a', nextId: 'c', index: 2, total: 5 });
    render(<GRNNavigation grnId="b" />);
    fireEvent.click(screen.getByRole('button', { name: /next grn/i }));
    expect(pushMock).toHaveBeenCalledWith(
      '/procurement-management/grn/c?query=SPO-1&sort=picking_date&dir=desc&picking_status=approved',
    );
  });

  it('navigates to previous neighbour (no query -> no trailing ?)', () => {
    setNeighbours({ prevId: 'a', nextId: 'c', index: 2, total: 5 });
    render(<GRNNavigation grnId="b" />);
    fireEvent.click(screen.getByRole('button', { name: /previous grn/i }));
    expect(pushMock).toHaveBeenCalledWith('/procurement-management/grn/a');
  });
});
