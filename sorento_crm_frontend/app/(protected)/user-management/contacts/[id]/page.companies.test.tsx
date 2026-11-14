/**
 * CONTACT-COMPANIES-COL (owner 14 Nov: the list "should follow the detail page"; crew 14 Nov: company
 * access stays superadmin-only to read, PLAN-user-management-read-gates.md:138). The detail page's
 * Companies field is the same company access the list column shows: a superadmin sees it, anyone
 * else sees no Companies field at all (never "None - this contact receives no records", which is a
 * claim about data they may not read).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const viewer = vi.hoisted(() => ({ superadmin: true }));
const getContactCompaniesMock = vi.hoisted(() => vi.fn());

vi.mock('next-auth/react', () => ({ useSession: () => ({ data: { user: { email: 'admin@zzt.test' } } }) }));
vi.mock('@/lib/is-superadmin', () => ({ isSuperadminUser: () => viewer.superadmin }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn(async () => ({ ok: false, json: async () => ({}) })) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('./services/contactService', () => ({
  getContactCompanies: (...a: unknown[]) => getContactCompaniesMock(...a),
}));
vi.mock('./components/contact-context', () => ({
  useContact: () => ({
    contactId: 'contact-1',
    isLoading: false,
    contact: {
      id: 'contact-1', name: 'ZZT Contact', first_name: 'ZZT', last_name: 'Contact',
      phone_number: '+60100000031', access_types: [], access_type_codes: [],
    },
  }),
}));
const nothing = vi.hoisted(() => () => ({ default: () => null }));
vi.mock('./components/ContactTagSettingsSection', nothing);
vi.mock('./components/ContactCustomersSection', nothing);
vi.mock('./components/ContactUserAccountSection', nothing);
vi.mock('./components/ContactMarketSegmentSection', nothing);
vi.mock('./components/ContactAttachmentTypesSection', nothing);
vi.mock('./components/ContactPortalFormsSection', nothing);
vi.mock('./components/ContactEditDialog', nothing);
vi.mock('@/components/contacts/ContactBrandScopeSection', nothing);
vi.mock('@/components/stock-visibility/StockVisibilitySection', () => ({ StockVisibilitySection: () => null }));
vi.mock('@/components/spec-visibility/SpecVisibilitySection', () => ({ SpecVisibilitySection: () => null }));

import ContactProfilePage from './page';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactProfilePage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  viewer.superadmin = true;
  getContactCompaniesMock.mockResolvedValue([
    { id: 'co-m', name: 'Mocha' },
    { id: 'co-s', name: 'Sorento' },
  ]);
});
afterEach(() => cleanup());

describe('Contact detail - Companies (company access)', () => {
  it('a superadmin sees every company the contact has access to, via the shared service', async () => {
    renderPage();
    expect(await screen.findByText('Mocha')).toBeInTheDocument();
    expect(screen.getByText('Sorento')).toBeInTheDocument();
    expect(getContactCompaniesMock).toHaveBeenCalledWith('contact-1');
  });

  it('anyone else sees no Companies field and never the "receives no records" claim', async () => {
    viewer.superadmin = false;
    renderPage();
    await screen.findByText('Contact Information');
    expect(screen.queryByText('Companies')).toBeNull();
    expect(screen.queryByText(/receives no records/)).toBeNull();
    expect(getContactCompaniesMock).not.toHaveBeenCalled();
  });
});
