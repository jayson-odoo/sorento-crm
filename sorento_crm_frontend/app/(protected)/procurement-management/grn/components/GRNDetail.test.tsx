import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// --- mocks ----------------------------------------------------------------- //
const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('./GRNNavigation', () => ({
  default: () => <div data-testid="grn-navigation" />,
}));

vi.mock('./grn-delete-dialog', () => ({
  default: ({ open }: { open: boolean }) =>
    open ? <div data-testid="delete-dialog" /> : null,
}));

const grnMock = vi.fn();
const updateMutateAsync = vi.fn();
vi.mock('../hooks/useGRN', () => ({
  useGRN: () => grnMock(),
  useUpdateGRN: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
}));

import GRNDetail from './GRNDetail';

// Radix opens on pointer events jsdom does not synthesise from a plain click;
// keyboard activation is the pattern the other detail-header tests use.
function openGearMenu() {
  const trigger = screen.getByRole('button', { name: /grn options/i });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
}

const GRN = {
  id: 'grn-1',
  picking_number: 'GR-001114',
  spo_number: 'PO-000338',
  picking_date: '2026-06-22',
  picking_status: 'approved',
  picking_lines: [],
};

beforeEach(() => {
  pushMock.mockReset();
  updateMutateAsync.mockReset();
  grnMock.mockReturnValue({ data: GRN, isLoading: false });
});

describe('GRNDetail header', () => {
  it('renders the status as a soft pill, not a solid badge', () => {
    render(<GRNDetail grnId="grn-1" />);

    // Two pills: the one beside the title and the "Picking Status" field.
    const pills = screen.getAllByText('Approved');
    expect(pills.length).toBe(2);
    for (const pill of pills) {
      // The shared pastel palette from lib/status-pill, so GRN reads the same as
      // complaints / PR / SF rather than shouting in solid green.
      expect(pill.className).toContain('rounded-full');
      expect(pill.className).toContain('bg-blue-100');
      expect(pill.className).toContain('text-blue-800');
    }
  });

  it('offers a Back to GRN link, matching the users detail header', () => {
    render(<GRNDetail grnId="grn-1" />);

    const back = screen.getByRole('link', { name: /back to grn/i });
    expect(back).toHaveAttribute('href', '/procurement-management/grn');
  });

  it('keeps Delete out of the header and inside the gear menu', async () => {
    render(<GRNDetail grnId="grn-1" />);

    // Nothing delete-shaped is visible until the menu is opened.
    expect(screen.queryByRole('button', { name: /^delete/i })).toBeNull();

    openGearMenu();

    expect(
      await screen.findByRole('menuitem', { name: /delete grn/i }),
    ).toBeInTheDocument();
  });

  it('opens the confirm dialog from the menu rather than deleting outright', async () => {
    render(<GRNDetail grnId="grn-1" />);

    openGearMenu();
    expect(screen.queryByTestId('delete-dialog')).toBeNull();

    fireEvent.click(await screen.findByRole('menuitem', { name: /delete grn/i }));

    expect(screen.getByTestId('delete-dialog')).toBeInTheDocument();
  });

  it('still exposes the status changes it always did', async () => {
    render(<GRNDetail grnId="grn-1" />);

    openGearMenu();

    expect(await screen.findByRole('menuitem', { name: 'Draft' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Rejected' })).toBeInTheDocument();
    // The current status is not offered as a change.
    expect(screen.getByRole('menuitem', { name: 'Approved' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });
});
