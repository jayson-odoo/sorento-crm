/**
 * FORMS-TAG-CARD-FIX-A: the Portal forms group lists every kind the backend catalog offers, in the
 * catalog's order and with its labels; before the catalog arrives (or when it holds none) it falls
 * back to the frontend registry (lib/portal-form-kinds LANDING_KINDS / LANDING_LABELS).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, within, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LANDING_KINDS } from '@/lib/portal-form-kinds';

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/contact-tags/t1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

// The 11 kinds in backend order (portal_service.GRANTABLE_PORTAL_FORM_TYPES) with backend labels.
const CATALOG_FORMS = [
  ['complaint', 'Complaint'],
  ['stock_inquiry', 'Stock Inquiry'],
  ['purchase_request', 'Purchase Request'],
  ['sponsorship_form', 'Sponsorship Form'],
  ['project_registration', 'Project Registration'],
  ['price_tag_request', 'Price Tag Request'],
  ['sales_opportunity', 'Sales Opportunities'],
  ['sample_request', 'Sample Request'],
  ['new_product_application', 'New Product Application'],
  ['customer_asks', 'Customer asks'],
  ['conversation', 'Conversation'],
].map(([value, label]) => ({ value, label }));

let catalogBody: unknown = [];
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn((url: string) =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: async () => (String(url).includes('settings-catalog') ? catalogBody : []),
    }),
  ),
}));
vi.mock('../services/contactTagService', () => ({
  updateContactTag: vi.fn(),
  getContactTag: vi.fn(),
  getContactTags: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0 } }),
}));

import ContactTagSettings from './ContactTagSettings';

const SET = { complaint: true, stock_inquiry: true, purchase_request: false, sponsorship_form: true,
  price_tag_request: true, sales_opportunity: false, customer_asks: false, conversation: false };

function render(editing = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  rtlRender(
    <QueryClientProvider client={client}>
      <ContactTagSettings
        tag={{ id: 't1', name: 'Dealer', description: null, is_active: true, sort_order: 0,
          settings: { portal_forms: SET }, contact_count: 0, created_at: '', updated_at: '' } as never}
        editing={editing}
        onDone={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

const rowIds = () =>
  screen
    .getAllByTestId(/^setting-row-/)
    .map((n) => n.getAttribute('data-testid')!.replace('setting-row-', ''))
    .filter((k) => k !== 'requires_registered_project' && (LANDING_KINDS as readonly string[]).includes(k));

const checked = (key: string) =>
  within(screen.getByTestId(`setting-row-${key}`)).getByRole('radio', { checked: true }).textContent;

beforeEach(() => {
  catalogBody = [];
});

describe('Portal forms group rows', () => {
  it('lists all 11 catalog kinds in backend order; the 3 never set read Not set', async () => {
    catalogBody = { portal_forms: CATALOG_FORMS };
    render();
    await waitFor(() => expect(rowIds()).toEqual(CATALOG_FORMS.map((o) => o.value)));
    expect(screen.getByTestId('setting-row-sales_opportunity')).toHaveTextContent('Sales Opportunities');
    for (const k of ['project_registration', 'sample_request', 'new_product_application'])
      expect(checked(k)).toBe('Not set');
    expect(screen.getByTestId('setting-row-new_product_application')).toHaveTextContent('New Product Application');
    expect(checked('complaint')).toBe('On');
  });

  it('with no catalog kinds it falls back to the frontend registry', async () => {
    render();
    await waitFor(() => expect(rowIds()).toEqual([...LANDING_KINDS]));
    expect(screen.getByTestId('setting-row-sample_request')).toHaveTextContent('Sample Request');
  });

  it('view mode lists only the set kinds, with the catalog labels', async () => {
    catalogBody = { portal_forms: CATALOG_FORMS };
    render(false);
    await waitFor(() =>
      expect(screen.getByTestId('setting-row-sales_opportunity')).toHaveTextContent('Sales Opportunities'),
    );
    expect(rowIds()).toEqual(Object.keys(SET));
    expect(screen.queryByTestId('setting-row-new_product_application')).toBeNull();
  });
});
