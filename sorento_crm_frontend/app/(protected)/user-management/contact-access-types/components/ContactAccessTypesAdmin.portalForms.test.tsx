/**
 * D61b / AC-M.27: the Portal forms field on a contact access type.
 *
 * The grant that decides whether a contact sees Price Tag Request in the portal
 * is `contact_access_types.portal_form_types`, and until this round it was
 * reachable only by SQL. These cover the two halves of the admin surface: the
 * list draws what a type carries, and the dialog edits it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/contact-access-types',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

// DataGrid persists column prefs via this hook (fires network) - stub it, or the
// grid renders skeletons forever and no row can be asserted.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const getAllContactAccessTypes = vi.fn();
const updateContactAccessType = vi.fn();
const createContactAccessType = vi.fn();
vi.mock('../services/contactAccessTypeService', () => ({
  getAllContactAccessTypes: (...a: unknown[]) => getAllContactAccessTypes(...a),
  updateContactAccessType: (...a: unknown[]) => updateContactAccessType(...a),
  createContactAccessType: (...a: unknown[]) => createContactAccessType(...a),
  deleteContactAccessType: vi.fn(),
  getContactAccessTypes: vi.fn(),
  getContactAccessType: vi.fn(),
}));

import ContactAccessTypesAdmin from './ContactAccessTypesAdmin';

const ROWS = [
  {
    code: 'dealer',
    name: 'Dealer',
    description: 'Sorento dealers',
    is_active: true,
    sort_order: 1,
    keywords: [],
    portal_form_types: ['stock_inquiry'],
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
  },
  {
    code: 'end_user',
    name: 'End User',
    description: null,
    is_active: true,
    sort_order: 2,
    keywords: [],
    portal_form_types: [],
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
  },
];

function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(
    <QueryClientProvider client={client}>
      <ContactAccessTypesAdmin />
    </QueryClientProvider>,
  );
}

const openMenu = () =>
  fireEvent.click(document.querySelector('[data-slot="searchable-multi-select-trigger"]')!);

async function openDealerDialog() {
  render();
  await screen.findByText('Dealer');
  const editButtons = screen.getAllByRole('button', { name: 'Edit' });
  fireEvent.click(editButtons[0]);
  await screen.findByText('Edit access type');
}

beforeEach(() => {
  vi.clearAllMocks();
  getAllContactAccessTypes.mockResolvedValue(ROWS);
  updateContactAccessType.mockResolvedValue(ROWS[0]);
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('ContactAccessTypesAdmin - the Portal forms column', () => {
  it('draws one chip per granted kind, labelled as the portal labels it', async () => {
    render();
    await screen.findByText('Dealer');

    expect(screen.getByText('Stock Inquiry')).toBeInTheDocument();
    // The row nobody granted anything to reads as a dash, not an empty cell.
    expect(screen.getByText('End User')).toBeInTheDocument();
  });

  it('does not show Price Tag Request for a type that was not granted it', async () => {
    render();
    await screen.findByText('Dealer');

    expect(screen.queryByText('Price Tag Request')).not.toBeInTheDocument();
  });

  it('shows Price Tag Request once the type carries it', async () => {
    getAllContactAccessTypes.mockResolvedValue([
      { ...ROWS[0], portal_form_types: ['stock_inquiry', 'price_tag_request'] },
      ROWS[1],
    ]);
    render();

    expect(await screen.findByText('Price Tag Request')).toBeInTheDocument();
  });
});

describe('ContactAccessTypesAdmin - the Portal forms field', () => {
  it('offers all five kinds with the portal labels', async () => {
    await openDealerDialog();
    openMenu();

    await waitFor(() =>
      expect(screen.getAllByText('Purchase Request').length).toBeGreaterThan(0),
    );
    for (const label of [
      'Complaint',
      'Stock Inquiry',
      'Purchase Request',
      'Sponsorship Form',
      'Price Tag Request',
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it('opens with the row current kinds already selected', async () => {
    await openDealerDialog();

    const trigger = document.querySelector('[data-slot="searchable-multi-select-trigger"]')!;
    expect(trigger.textContent).toContain('Stock Inquiry');
    expect(trigger.textContent).not.toContain('Price Tag Request');
  });

  it('submits the chosen codes when the grant is added', async () => {
    await openDealerDialog();
    openMenu();

    await waitFor(() =>
      expect(screen.getAllByText('Price Tag Request').length).toBeGreaterThan(0),
    );
    fireEvent.click(screen.getAllByText('Price Tag Request')[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));

    await waitFor(() => expect(updateContactAccessType).toHaveBeenCalled());
    const [code, body] = updateContactAccessType.mock.calls[0];
    expect(code).toBe('dealer');
    expect(body.portal_form_types).toEqual(['stock_inquiry', 'price_tag_request']);
  });

  it('submits the shorter list when the grant is taken back', async () => {
    getAllContactAccessTypes.mockResolvedValue([
      { ...ROWS[0], portal_form_types: ['stock_inquiry', 'price_tag_request'] },
      ROWS[1],
    ]);
    await openDealerDialog();
    openMenu();

    await waitFor(() =>
      expect(screen.getAllByText('Price Tag Request').length).toBeGreaterThan(0),
    );
    // The last match is the option row; the first is the trigger chip.
    const options = screen.getAllByText('Price Tag Request');
    fireEvent.click(options[options.length - 1]);
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));

    await waitFor(() => expect(updateContactAccessType).toHaveBeenCalled());
    expect(updateContactAccessType.mock.calls[0][1].portal_form_types).toEqual(['stock_inquiry']);
  });

  it('a new type is created with no portal forms unless one is picked', async () => {
    createContactAccessType.mockResolvedValue(ROWS[1]);
    render();
    await screen.findByText('Dealer');
    fireEvent.click(screen.getByRole('button', { name: /add type/i }));
    await screen.findByText('Add access type');

    fireEvent.change(screen.getByLabelText('Code'), { target: { value: 'zzt_new' } });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'ZZT New' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createContactAccessType).toHaveBeenCalled());
    expect(createContactAccessType.mock.calls[0][0].portal_form_types).toEqual([]);
  });
});
