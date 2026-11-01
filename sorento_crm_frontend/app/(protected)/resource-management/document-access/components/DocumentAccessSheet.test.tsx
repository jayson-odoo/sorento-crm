/**
 * The row Sheet of the Document Access page (DAS-FE-5, DAS-FE-8 for the sheet).
 *
 * Rendered through `DocumentAccessView` and opened by clicking a row, so the test does not depend on the
 * sheet's props. `AccessLevelsMultiSelect` is stubbed to one button per access type so the test holds
 * "levels edit through the existing component and the existing attachment update" without driving a
 * Radix dropdown in jsdom.
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
  updateAttachment: vi.fn(),
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
vi.mock('../../attachments/services/attachmentService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../attachments/services/attachmentService')>()),
  updateAttachment: (...a: unknown[]) => svc.updateAttachment(...a),
}));
vi.mock('../../attachments/components/AccessLevelsMultiSelect', () => ({
  AccessLevelsMultiSelect: ({ options, value, onChange }: { options: { code: string; name?: string }[]; value: string[]; onChange: (v: string[]) => void }) => (
    <div data-testid="levels" data-value={value.join(',')}>
      {options.map((o) => (
        <button key={o.code} type="button" onClick={() => onChange([...new Set([...value, o.code])])}>
          {`add level ${o.name ?? o.code}`}
        </button>
      ))}
    </div>
  ),
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
  CONTACT_A, CONTACTS_VIEW, DOCS, EDIT, TECH, UUID_RE, VIEW, matrix, matrixFor, renderWithClient,
} from './documentAccess.testFixtures';

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  held.slugs = new Set([VIEW, EDIT, CONTACTS_VIEW]);
  svc.getDocumentAccess.mockImplementation(async (arg?: { contactId?: string }) => (arg?.contactId ? matrixFor() : matrix()));
  svc.getDocumentAccessDocuments.mockResolvedValue(DOCS);
  svc.searchPreviewContacts.mockResolvedValue([{ id: CONTACT_A, name: 'CONTACT A' }]);
  svc.updateAttachmentType.mockResolvedValue({});
  svc.updateAttachment.mockResolvedValue({});
});

async function openSheet(name = 'Technical Specifications') {
  renderWithClient(<DocumentAccessView />);
  await screen.findByText(name);
  fireEvent.click(screen.getByRole('row', { name: new RegExp(name) }));
  return screen.findByRole('dialog');
}

describe('DocumentAccessSheet (DAS-FE-5)', () => {
  it('opens on a row click with the name, Shared badge, file counts and its three sections', async () => {
    const dialog = await openSheet();

    expect(within(dialog).getByText('Technical Specifications')).toBeInTheDocument();
    expect(within(dialog).getByText('Shared')).toBeInTheDocument();
    expect(within(dialog).getByText(/4 files\s*·\s*3 readable/)).toBeInTheDocument();
    expect(within(dialog).getByText('Who can read')).toBeInTheDocument();
    expect(within(dialog).getByText('Documents')).toBeInTheDocument();
    expect(within(dialog).getByText('Sent as a file')).toBeInTheDocument();
  });

  it('lists the documents with file name, access levels and company or Shared, paginated by the service', async () => {
    const dialog = await openSheet();

    expect(await within(dialog).findByText('Cabana Warranty.pdf')).toBeInTheDocument();
    expect(within(dialog).getByText('Tile Care.docx')).toBeInTheDocument();
    expect(within(dialog).getByText('Sorento')).toBeInTheDocument();
    expect(within(dialog).getAllByText('Shared').length).toBeGreaterThanOrEqual(2); // the type badge + the shared file
    expect(svc.getDocumentAccessDocuments).toHaveBeenCalledWith(TECH, expect.objectContaining({ page: 1, limit: 50 }));
    expect(document.body.textContent ?? '').not.toMatch(UUID_RE);
  });

  it('asks for the verdicts of the previewed contact', async () => {
    renderWithClient(<DocumentAccessView />);
    await screen.findByText('Technical Specifications');
    fireEvent.click(screen.getByRole('combobox', { name: /Preview as/i }));
    fireEvent.click(await screen.findByRole('option', { name: 'CONTACT A' }));
    await screen.findByText(/Runs as/);

    fireEvent.click(screen.getByRole('row', { name: /Technical Specifications/ }));
    await screen.findByRole('dialog');

    await waitFor(() =>
      expect(svc.getDocumentAccessDocuments).toHaveBeenCalledWith(TECH, expect.objectContaining({ contactId: CONTACT_A })),
    );
  });

  it('a Who can read chip saves like the grid tick, with the same toast', async () => {
    const dialog = await openSheet();

    fireEvent.click(within(dialog).getByText('End User'));

    await waitFor(() => expect(svc.updateAttachmentType).toHaveBeenCalledWith(TECH, { ai_read_codes: ['dealer', 'end_user'] }));
    await waitFor(() =>
      expect(svc.toast.success).toHaveBeenCalledWith('Technical Specifications: End User can now read 3 documents.', expect.anything()),
    );
  });

  it('editing one document\'s access levels uses the attachment update', async () => {
    const dialog = await openSheet();
    await within(dialog).findByText('Cabana Warranty.pdf');

    fireEvent.click(within(dialog).getAllByRole('button', { name: 'add level End User' })[0]);

    await waitFor(() =>
      expect(svc.updateAttachment).toHaveBeenCalledWith('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', {
        access_levels: ['dealer', 'end_user'],
      }),
    );
  });

  it('only documents with can_edit_levels get an editable levels control (R5)', async () => {
    const dialog = await openSheet();
    await within(dialog).findByText('Cabana Warranty.pdf');

    expect(within(dialog).getAllByTestId('levels')).toHaveLength(1);
    expect(within(dialog).getAllByRole('button', { name: 'add level End User' })).toHaveLength(1);
    // The read-only document still shows its levels, as plain text.
    expect(within(dialog).getByText('Tile Care.docx')).toBeInTheDocument();
  });

  it('disables the sheet chips while a tick save is pending (R3)', async () => {
    svc.updateAttachmentType.mockImplementation(() => new Promise(() => {}));
    const dialog = await openSheet();

    fireEvent.click(within(dialog).getByText('End User'));

    await waitFor(() => expect(within(dialog).getByText('End User').closest('button')).toBeDisabled());
    expect(within(dialog).getByText('Dealer').closest('button')).toBeDisabled();
    expect(within(dialog).getByText('Staff').closest('button')).toBeDisabled();
    expect(svc.updateAttachmentType).toHaveBeenCalledTimes(1);
  });

  it('shows the Direct access switch and "Granted to N contacts"; flipping it saves is_direct_access', async () => {
    const dialog = await openSheet('Direct Access');

    expect(within(dialog).getByText(/Granted to 3 contacts/)).toBeInTheDocument();
    const sw = within(dialog).getByRole('switch');
    expect(sw).toBeChecked();

    fireEvent.click(sw);

    await waitFor(() => expect(svc.updateAttachmentType).toHaveBeenCalledWith(expect.any(String), { is_direct_access: false }));
    await waitFor(() => expect(svc.toast.success).toHaveBeenCalled());
  });

  it('is read-only without the edit permission: switch disabled, chips and levels do not save', async () => {
    held.slugs = new Set([VIEW, CONTACTS_VIEW]);
    const dialog = await openSheet('Direct Access');

    expect(within(dialog).getByRole('switch')).toBeDisabled();
    fireEvent.click(within(dialog).getByRole('switch'));
    expect(svc.updateAttachmentType).not.toHaveBeenCalled();
  });

  it('shows an empty state for a type with no documents, with no button', async () => {
    svc.getDocumentAccessDocuments.mockResolvedValue({ items: [], total: 0, page: 1, limit: 50 });
    const dialog = await openSheet('Empty Type');

    expect(await within(dialog).findByText(/No documents/i)).toBeInTheDocument();
  });
});
