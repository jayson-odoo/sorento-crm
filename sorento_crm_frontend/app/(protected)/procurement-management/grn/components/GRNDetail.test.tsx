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
// The gear resolves permissions; this test has no session or query client, and
// RBAC has its own tests.
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

vi.mock('../hooks/useGRN', () => ({
  useGRN: () => grnMock(),
  useUpdateGRN: () => ({ mutate: updateMutateAsync, mutateAsync: updateMutateAsync, isPending: false }),
  grnPagerQuery: {
    listQueryKey: () => ['grn'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
}));

// The pager has its own tests (hooks/useListPager.test.ts).
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

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

  it('S3-02: leaves Back to the toolbar row and keeps only pager, gear and Edit', () => {
    render(<GRNDetail grnId="grn-1" />);

    // Back moved to the page's toolbar row (D6), so the record card no longer
    // carries it; the page renders it beside the breadcrumb.
    expect(screen.queryByRole('link', { name: /back to grn/i })).toBeNull();
    expect(screen.getByRole('button', { name: /grn options/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^edit$/i })).toBeTruthy();
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

  it('names who created the GRN and where it came from', () => {
    grnMock.mockReturnValue({
      data: {
        ...GRN,
        created_by_label: 'Datun',
        source_system: 'import',
        import_filename: 'GRN Listing 06.08.2026 am.xlsx',
      },
      isLoading: false,
    });
    render(<GRNDetail grnId="grn-1" />);

    expect(screen.getByText(/Datun/)).toBeInTheDocument();
    expect(screen.getByText(/Excel import/)).toBeInTheDocument();
    expect(
      screen.getByText(/GRN Listing 06\.08\.2026 am\.xlsx/),
    ).toBeInTheDocument();
  });

  it('says Unknown rather than hiding the section on an unattributed GRN', () => {
    // Rows created before provenance was recorded. An absent section reads as
    // "no such concept"; "Unknown" reads as "we do not know", which is the truth.
    render(<GRNDetail grnId="grn-1" />);

    expect(screen.getByText('Created by')).toBeInTheDocument();
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  it('labels an integration-created GRN as the integration, not a person', () => {
    grnMock.mockReturnValue({
      data: { ...GRN, created_by_label: null, source_system: 'external_api' },
      isLoading: false,
    });
    render(<GRNDetail grnId="grn-1" />);

    expect(screen.getByText(/AutoCount \/ n8n integration/)).toBeInTheDocument();
  });

  it('S3-07: still exposes the status changes it always did, as the shared action set', async () => {
    render(<GRNDetail grnId="grn-1" />);

    openGearMenu();

    expect(await screen.findByRole('menuitem', { name: 'Mark as Draft' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Mark as Rejected' })).toBeInTheDocument();
    // The status the GRN already has is not a change, so it is not offered at
    // all rather than offered and disabled.
    expect(screen.queryByRole('menuitem', { name: /Approved/ })).toBeNull();
  });
});
