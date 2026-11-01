/**
 * DocumentAccessView (DAS-FE-2 .. DAS-FE-4, DAS-FE-7 states, DAS-FE-8).
 *
 * The service layer is mocked (`../services/documentAccessService`, the attachment type update, sonner)
 * so the test holds the page's contract: a DataGrid of types, a Staff tick plus one tick per active
 * access type, amber reach, save-on-click with a counted toast, a "Preview as" contact picker.
 * Rows are located by the type name; ticks by column position: [Staff, ...access types in order].
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

const held = vi.hoisted(() => ({ slugs: new Set<string>() }));
const svc = vi.hoisted(() => ({
  getDocumentAccess: vi.fn(),
  getDocumentAccessDocuments: vi.fn(),
  searchPreviewContacts: vi.fn(),
  updateAttachmentType: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../services/documentAccessService', () => ({
  getDocumentAccess: (...a: unknown[]) => svc.getDocumentAccess(...a),
  getDocumentAccessDocuments: (...a: unknown[]) => svc.getDocumentAccessDocuments(...a),
  searchPreviewContacts: (...a: unknown[]) => svc.searchPreviewContacts(...a),
}));
vi.mock('../../attachment-types/services/attachmentTypeService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../attachment-types/services/attachmentTypeService')>()),
  updateAttachmentType: (...a: unknown[]) => svc.updateAttachmentType(...a),
}));
vi.mock('sonner', () => ({ toast: svc.toast, Toaster: () => null }));
vi.mock('@/hooks/usePermissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/usePermissions')>()),
  useHasPermission: (slug: string) => held.slugs.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.slugs.has(s)),
  usePermissions: () => ({
    permissions: [...held.slugs], permissionSet: held.slugs, isLoading: false, isError: false,
    isFetching: false, error: null, refetch: vi.fn(),
  }),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/resource-management/document-access',
}));
vi.mock('@/app/providers/CompanyProvider', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/app/providers/CompanyProvider')>()),
  useCompany: () => ({ activeCompany: { id: 'company-1', name: 'Sorento' } }),
}));

import { DocumentAccessView } from './DocumentAccessView';
import {
  ALPHA, CONTACT_A, CONTACT_BLOCK, CONTACTS_VIEW, DIRECT, EDIT, EMPTY, TECH, UUID_RE, VIEW,
  matrix, matrixFor, renderWithClient,
} from './documentAccess.testFixtures';

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  held.slugs = new Set([VIEW, EDIT, CONTACTS_VIEW]);
  svc.getDocumentAccess.mockResolvedValue(matrix());
  svc.getDocumentAccessDocuments.mockResolvedValue({ items: [], total: 0, page: 1, limit: 50 });
  svc.searchPreviewContacts.mockResolvedValue([{ id: CONTACT_A, name: 'CONTACT A' }]);
  svc.updateAttachmentType.mockResolvedValue({});
});

const rowOf = (name: string | RegExp) => screen.getByRole('row', { name: typeof name === 'string' ? new RegExp(name) : name });
/** Ticks of a row in column order: [Staff, Dealer, End User, Mocha Dealer]. */
const ticks = (name: string) => within(rowOf(name)).getAllByRole('checkbox');

async function renderView() {
  renderWithClient(<DocumentAccessView />);
  await screen.findByText('Technical Specifications');
}

describe('DocumentAccessView - page and grid (DAS-FE-2)', () => {
  it('renders a "Document Access" header with no CTA and one column per active access type', async () => {
    await renderView();

    expect(screen.getByRole('heading', { name: 'Document Access' })).toBeInTheDocument();
    for (const header of ['Type', 'Documents']) {
      expect(screen.getByRole('columnheader', { name: new RegExp(`^${header}`) })).toBeInTheDocument();
    }
    for (const header of ['Staff', 'Dealer', 'End User', 'Mocha Dealer']) {
      expect(screen.getByRole('columnheader', { name: new RegExp(`^${header}$`) })).toBeInTheDocument();
    }
    expect(screen.getByRole('columnheader', { name: /Sent as a file/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^(Add|Create|New)/i })).not.toBeInTheDocument();
    expect(svc.getDocumentAccess).toHaveBeenCalledWith(expect.objectContaining({}));
  });

  it('shows the type, document and sent-as-a-file cells', async () => {
    await renderView();

    expect(within(rowOf('Technical Specifications')).getByText(/Shared\s*·\s*4 files/)).toBeInTheDocument();
    expect(within(rowOf('Technical Specifications')).getByText(/3 readable/)).toBeInTheDocument();
    expect(within(rowOf('Empty Type')).getByText(/none readable/)).toBeInTheDocument();
    expect(within(rowOf('Direct Access')).getByText('Direct access')).toBeInTheDocument();
    expect(within(rowOf('Direct Access')).getByText(/Granted to 3/)).toBeInTheDocument();
    expect(within(rowOf('Technical Specifications')).queryByText('Direct access')).not.toBeInTheDocument();
  });

  it('sorts rows by readable documents, then name', async () => {
    await renderView();

    const names = screen.getAllByRole('row').slice(1).map((r) => r.textContent ?? '');
    const order = ['Direct Access', 'Technical Specifications', 'Alpha Zero', 'Empty Type'].map((n) =>
      names.findIndex((t) => t.includes(n)),
    );
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it('filters by type name and shows "No types match" with no button when nothing matches', async () => {
    await renderView();

    fireEvent.change(screen.getByPlaceholderText(/Search/i), { target: { value: 'zzz-nothing' } });

    expect(await screen.findByText('No types match')).toBeInTheDocument();
    expect(screen.queryByText('Technical Specifications')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reset|add|create|new/i })).not.toBeInTheDocument();
  });

  it('the AI reads filter keeps on-types or off-types', async () => {
    await renderView();

    fireEvent.click(screen.getByRole('combobox', { name: /AI reads/i }));
    fireEvent.click(await screen.findByRole('option', { name: 'On' }));
    await waitFor(() => expect(screen.queryByText('Empty Type')).not.toBeInTheDocument());
    expect(screen.getByText('Technical Specifications')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('combobox', { name: /AI reads/i }));
    fireEvent.click(await screen.findByRole('option', { name: 'Off' }));
    await waitFor(() => expect(screen.queryByText('Technical Specifications')).not.toBeInTheDocument());
    expect(screen.getByText('Empty Type')).toBeInTheDocument();
  });
});

describe('DocumentAccessView - states (DAS-FE-7)', () => {
  it('shows the header while loading and no "No types match" yet', async () => {
    svc.getDocumentAccess.mockReturnValue(new Promise(() => {}));
    renderWithClient(<DocumentAccessView />);

    expect(screen.getByRole('heading', { name: 'Document Access' })).toBeInTheDocument();
    expect(screen.queryByText('No types match')).not.toBeInTheDocument();
    expect(screen.queryByText('Technical Specifications')).not.toBeInTheDocument();
  });

  it('shows the extracted error message in the grid body', async () => {
    svc.getDocumentAccess.mockRejectedValue(new Error('The matrix could not be loaded.'));
    renderWithClient(<DocumentAccessView />);

    expect(await screen.findByText(/The matrix could not be loaded\./)).toBeInTheDocument();
  });
});

describe('DocumentAccessView - ticks (DAS-FE-3)', () => {
  it('shows the ticked state of Staff and each access type', async () => {
    await renderView();

    const [staff, dealer, endUser, mocha] = ticks('Technical Specifications');
    expect(staff).toBeChecked();
    expect(dealer).toBeChecked();
    expect(endUser).not.toBeChecked();
    expect(mocha).not.toBeChecked();
  });

  it('shows reach/readable in the warning colour, with a title, only on a ticked cell that falls short', async () => {
    await renderView();

    const reach = within(rowOf('Technical Specifications')).getByText('2/3');
    expect(reach.closest('[title]')).not.toBeNull();
    expect(reach.closest('[class*="warning"], [class*="amber"]')).not.toBeNull();
    // End User reaches 3/3 and is unticked: nothing is shown for it.
    expect(within(rowOf('Technical Specifications')).queryByText('3/3')).not.toBeInTheDocument();
  });

  it('ticking an access type saves the full list in catalogue order and toasts the count', async () => {
    await renderView();

    fireEvent.click(ticks('Technical Specifications')[2]); // End User

    await waitFor(() =>
      expect(svc.updateAttachmentType).toHaveBeenCalledWith(TECH, { ai_read_codes: ['dealer', 'end_user'] }),
    );
    await waitFor(() =>
      expect(svc.toast.success).toHaveBeenCalledWith('Technical Specifications: End User can now read 3 documents.', expect.anything()),
    );
  });

  it('unticking says "no longer reads"', async () => {
    await renderView();

    fireEvent.click(ticks('Technical Specifications')[1]); // Dealer

    await waitFor(() => expect(svc.updateAttachmentType).toHaveBeenCalledWith(TECH, { ai_read_codes: [] }));
    await waitFor(() =>
      expect(svc.toast.success).toHaveBeenCalledWith('Technical Specifications: Dealer no longer reads 2 documents.', expect.anything()),
    );
  });

  it('the Staff tick saves ai_read_staff and counts the readable documents', async () => {
    await renderView();

    fireEvent.click(ticks('Technical Specifications')[0]);

    await waitFor(() => expect(svc.updateAttachmentType).toHaveBeenCalledWith(TECH, { ai_read_staff: false }));
    await waitFor(() =>
      expect(svc.toast.success).toHaveBeenCalledWith('Technical Specifications: Staff no longer reads 3 documents.', expect.anything()),
    );
  });

  it('an error shows the message and the tick returns to its saved state', async () => {
    svc.updateAttachmentType.mockRejectedValue(new Error('That access type is not active.'));
    await renderView();
    const endUser = ticks('Technical Specifications')[2];

    fireEvent.click(endUser);

    await waitFor(() => expect(svc.toast.error).toHaveBeenCalledWith(expect.stringContaining('That access type is not active.'), expect.anything()));
    await waitFor(() => expect(ticks('Technical Specifications')[2]).not.toBeChecked());
    expect(svc.toast.success).not.toHaveBeenCalled();
  });

  it('without the edit permission the ticks are read-only', async () => {
    held.slugs = new Set([VIEW, CONTACTS_VIEW]);
    await renderView();

    const all = ticks('Technical Specifications');
    expect(all[0]).toBeChecked();
    all.forEach((cb) => expect(cb).toBeDisabled());
    fireEvent.click(all[2]);
    expect(svc.updateAttachmentType).not.toHaveBeenCalled();
  });
});

describe('DocumentAccessView - a pending tick save (R3)', () => {
  it('disables that row\'s ticks until the save resolves and the row refreshes; the next tick builds on the saved list', async () => {
    let saved = ['dealer'];
    let release: (v?: unknown) => void = () => {};
    svc.getDocumentAccess.mockImplementation(async () =>
      matrix({ rows: matrix().rows.map((r) => (r.id === TECH ? { ...r, ai_read_codes: saved } : r)) }),
    );
    svc.updateAttachmentType.mockImplementationOnce(
      (_id: string, body: { ai_read_codes: string[] }) =>
        new Promise((resolve) => {
          release = () => {
            saved = body.ai_read_codes;
            resolve({});
          };
        }),
    );
    await renderView();

    fireEvent.click(ticks('Technical Specifications')[1]); // untick Dealer: [] , pending

    await waitFor(() => ticks('Technical Specifications').forEach((cb) => expect(cb).toBeDisabled()));
    ticks('Direct Access').forEach((cb) => expect(cb).not.toBeDisabled());
    expect(svc.updateAttachmentType).toHaveBeenCalledTimes(1);

    release();

    await waitFor(() => ticks('Technical Specifications').forEach((cb) => expect(cb).not.toBeDisabled()));
    fireEvent.click(ticks('Technical Specifications')[2]); // End User, on top of the SAVED []
    await waitFor(() => expect(svc.updateAttachmentType).toHaveBeenCalledTimes(2));
    expect(svc.updateAttachmentType).toHaveBeenLastCalledWith(TECH, { ai_read_codes: ['end_user'] });
  });
});

describe('DocumentAccessView - the row lock holds until the refresh resolves (B2, M3)', () => {
  it('B2: after the PUT resolves the row stays locked until the matrix refetch resolves', async () => {
    let releaseRefetch: (v?: unknown) => void = () => {};
    let calls = 0;
    svc.getDocumentAccess.mockImplementation(() => {
      calls += 1;
      return calls === 1
        ? Promise.resolve(matrix())
        : new Promise((resolve) => {
            releaseRefetch = () => resolve(matrix());
          });
    });
    await renderView();

    fireEvent.click(ticks('Technical Specifications')[2]); // End User: PUT resolves at once

    await waitFor(() => expect(svc.updateAttachmentType).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2)); // the refetch is in flight, held open
    ticks('Technical Specifications').forEach((cb) => expect(cb).toBeDisabled());

    releaseRefetch();

    await waitFor(() => ticks('Technical Specifications').forEach((cb) => expect(cb).not.toBeDisabled()));
  });

  it('M3: ticking row B while row A is pending leaves row A locked until A saves and refreshes', async () => {
    let releaseA: (v?: unknown) => void = () => {};
    svc.updateAttachmentType.mockImplementation((id: string) =>
      id === TECH
        ? new Promise((resolve) => {
            releaseA = () => resolve({});
          })
        : Promise.resolve({}),
    );
    await renderView();

    fireEvent.click(ticks('Technical Specifications')[2]); // A pending
    await waitFor(() => ticks('Technical Specifications').forEach((cb) => expect(cb).toBeDisabled()));
    fireEvent.click(ticks('Direct Access')[2]); // B, while A is pending

    await waitFor(() => expect(svc.updateAttachmentType).toHaveBeenCalledTimes(2));
    await waitFor(() => ticks('Direct Access').forEach((cb) => expect(cb).not.toBeDisabled()));
    ticks('Technical Specifications').forEach((cb) => expect(cb).toBeDisabled());

    releaseA();

    await waitFor(() => ticks('Technical Specifications').forEach((cb) => expect(cb).not.toBeDisabled()));
  });
});

describe('DocumentAccessView - Preview as (DAS-FE-4)', () => {
  async function pickContact() {
    fireEvent.click(screen.getByRole('combobox', { name: /Preview as/i }));
    fireEvent.click(await screen.findByRole('option', { name: 'CONTACT A' }));
  }

  it('picking a contact refetches with that contact and shows the strip', async () => {
    svc.getDocumentAccess.mockImplementation(async (arg?: { contactId?: string }) =>
      arg?.contactId ? matrixFor() : matrix(),
    );
    await renderView();

    await pickContact();

    await waitFor(() => expect(svc.getDocumentAccess).toHaveBeenCalledWith(expect.objectContaining({ contactId: CONTACT_A })));
    expect(await screen.findByText(/Runs as/)).toBeInTheDocument();
    expect(screen.getByText(/Agent on WhatsApp/)).toBeInTheDocument();
    expect(screen.getByText(/Access types/)).toBeInTheDocument();
    expect(screen.getByText(/Companies/)).toBeInTheDocument();
    expect(screen.getByText('Sorento')).toBeInTheDocument();
  });

  it('shows a verdict pill per row, with the counts, and highlights the contact\'s columns', async () => {
    svc.getDocumentAccess.mockImplementation(async (arg?: { contactId?: string }) =>
      arg?.contactId ? matrixFor() : matrix(),
    );
    await renderView();

    await pickContact();

    const direct = await within(rowOf('Direct Access')).findByText(/Reads 5 of 15/);
    expect(direct.textContent).toMatch(/2 no shared access type/);
    expect(direct.textContent).toMatch(/8 other company/);
    expect(within(rowOf('Technical Specifications')).getByText(/Not ticked for End User/)).toBeInTheDocument();
    // The contact holds End User only: that column header carries data-contact-access="true", the others do not.
    expect(screen.getByRole('columnheader', { name: /^End User$/ })).toHaveAttribute('data-contact-access', 'true');
    expect(screen.getByRole('columnheader', { name: /^Dealer$/ })).not.toHaveAttribute('data-contact-access', 'true');
  });

  it('highlights the contact\'s access-type columns with a class on the header AND the cells (R4)', async () => {
    svc.getDocumentAccess.mockImplementation(async (arg?: { contactId?: string }) =>
      arg?.contactId ? matrixFor() : matrix(),
    );
    await renderView();
    await pickContact();
    await screen.findByText(/Runs as/);

    expect(screen.getByRole('columnheader', { name: /^End User$/ }).className).toMatch(/bg-primary\/5/);
    expect(screen.getByRole('columnheader', { name: /^Dealer$/ }).className).not.toMatch(/bg-primary\/5/);
    // Cells: the End User tick sits in a highlighted cell on every row; the Dealer tick does not.
    for (const name of ['Technical Specifications', 'Direct Access']) {
      const [, dealer, endUser] = ticks(name);
      expect(endUser.closest('td')?.className).toMatch(/bg-primary\/5/);
      expect(dealer.closest('td')?.className ?? '').not.toMatch(/bg-primary\/5/);
    }
  });

  it('a blocked contact reads "No access type" on every row', async () => {
    svc.getDocumentAccess.mockImplementation(async (arg?: { contactId?: string }) =>
      arg?.contactId ? matrixFor({ ...CONTACT_BLOCK, access_types: [], blocked: 'no_access_type' }) : matrix(),
    );
    await renderView();

    await pickContact();

    await waitFor(() => expect(within(rowOf('Direct Access')).getByText(/No access type/)).toBeInTheDocument());
    expect(within(rowOf('Technical Specifications')).getByText(/No access type/)).toBeInTheDocument();
  });

  it('clearing the contact returns to the plain matrix', async () => {
    svc.getDocumentAccess.mockImplementation(async (arg?: { contactId?: string }) =>
      arg?.contactId ? matrixFor() : matrix(),
    );
    await renderView();
    await pickContact();
    await screen.findByText(/Runs as/);

    fireEvent.pointerDown(screen.getByRole('button', { name: /Clear selection/i }));

    await waitFor(() => expect(screen.queryByText(/Runs as/)).not.toBeInTheDocument());
  });

  it('is hidden without user_management.contacts.view', async () => {
    held.slugs = new Set([VIEW, EDIT]);
    await renderView();

    expect(screen.queryByRole('combobox', { name: /Preview as/i })).not.toBeInTheDocument();
  });
});

describe('DocumentAccessView - no UUID on screen (DAS-FE-8)', () => {
  it('renders no text that looks like an id, with and without a contact', async () => {
    svc.getDocumentAccess.mockImplementation(async (arg?: { contactId?: string }) =>
      arg?.contactId ? matrixFor() : matrix(),
    );
    await renderView();
    expect(document.body.textContent ?? '').not.toMatch(UUID_RE);
    expect([DIRECT, EMPTY, ALPHA].some((id) => (document.body.textContent ?? '').includes(id))).toBe(false);

    fireEvent.click(screen.getByRole('combobox', { name: /Preview as/i }));
    fireEvent.click(await screen.findByRole('option', { name: 'CONTACT A' }));
    await screen.findByText(/Runs as/);
    expect(document.body.textContent ?? '').not.toMatch(UUID_RE);
  });
});
