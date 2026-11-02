/**
 * The phone layout of Document Access (DAS-FE-7 cards; fix round R8 keyboard + amber reach, R3 pending).
 * `matchMedia` answers "matches" so the page draws cards instead of the grid.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

(window as unknown as { matchMedia: unknown }).matchMedia = (query: string) => ({
  matches: true, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
});
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
import { CONTACTS_VIEW, DOCS, EDIT, VIEW, matrix, renderWithClient } from './documentAccess.testFixtures';

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  held.slugs = new Set([VIEW, EDIT, CONTACTS_VIEW]);
  svc.getDocumentAccess.mockResolvedValue(matrix());
  svc.getDocumentAccessDocuments.mockResolvedValue(DOCS);
  svc.searchPreviewContacts.mockResolvedValue([]);
  svc.updateAttachmentType.mockResolvedValue({});
});

const cardOf = () => screen.getByText('Technical Specifications').closest('li') as HTMLElement;

async function renderPhone() {
  renderWithClient(<DocumentAccessView />);
  await screen.findByText('Technical Specifications');
}

describe('DocumentAccessView on a phone', () => {
  it('draws cards, not a table', async () => {
    await renderPhone();

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(cardOf()).toBeInTheDocument();
  });

  it('the card is keyboard reachable: a button named for the type, and Enter opens the sheet (R8)', async () => {
    await renderPhone();

    const opener = screen.getByRole('button', { name: /^(Open )?Technical Specifications/ });
    opener.focus();
    expect(opener).toHaveFocus();
    await userEvent.keyboard('{Enter}');

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('shows the amber reach count on a short ticked chip, like the grid (R8)', async () => {
    await renderPhone();

    const reach = within(cardOf()).getByText('2/3');
    expect(reach.closest('[title]')).not.toBeNull();
    expect(reach.closest('[class*="warning"], [class*="amber"]')).not.toBeNull();
  });

  it('disables every chip of a card while its tick save is pending (R3)', async () => {
    svc.updateAttachmentType.mockImplementation(() => new Promise(() => {}));
    await renderPhone();

    fireEvent.click(within(cardOf()).getByRole('checkbox', { name: 'End User reads Technical Specifications' }));

    await waitFor(() =>
      within(cardOf()).getAllByRole('checkbox').forEach((chip) => expect(chip).toBeDisabled()),
    );
    expect(svc.updateAttachmentType).toHaveBeenCalledTimes(1);
  });
});
