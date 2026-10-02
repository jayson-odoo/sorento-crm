/**
 * Access model S6 (AC-AM-7). Red test: the Access tab still renders the Access Agents grid and the
 * Field reveals card; it must instead render roles + the tree under "What the chatbot answers".
 * Hook names pinned (hooks/useChatbotAccess.ts): useChatbotRegistry, useChatbotRoles,
 * useContactAccess(contactId), useSetContactAccess(contactId).
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactAccessPage from './page';

vi.mock('@/lib/api', () => ({ apiFetch: () => new Promise(() => {}) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({ id: 'c1' }),
  usePathname: () => '/user-management/contacts/c1/access',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('../components/contact-context', () => ({
  useContact: () => ({ isLoading: false, contactId: 'c1' }),
}));
vi.mock('../components/ContactMediaAccessSection', () => ({
  default: () => <div>media-access-stub</div>,
}));
vi.mock('@/hooks/useChatbotAccess', () => ({
  useChatbotRegistry: () => ({
    data: {
      domains: [
        { name: 'incoming', label: 'Incoming stock', supported: true, access_section: null, escalation_agent_code: 'inc', escalation_team_code: 'purchasing',
          fields: [{ key: 'incoming.eta', label: 'ETA', kind: 'field' }, { key: 'incoming.consignee', label: 'Consignee', kind: 'field' }] },
      ],
    },
    isLoading: false,
    isError: false,
  }),
  useChatbotRoles: () => ({ data: [{ id: 'r1', code: 'purchasing', name: 'Purchasing', domains: ['incoming'], fields: ['incoming.eta'], contact_count: 5 }], isLoading: false, isError: false }),
  useContactAccess: () => ({
    data: {
      roles: [{ id: 'r1', code: 'purchasing', name: 'Purchasing' }],
      overrides: [{ domain_name: 'incoming', field_key: 'incoming.consignee', granted: true }],
      effective: { domains: ['incoming'], attributes: ['incoming.eta', 'incoming.consignee'], sees_all_customers: true },
    },
    isLoading: false,
    isError: false,
  }),
  useSetContactAccess: () => ({ mutate: vi.fn(), isPending: false }),
}));

afterEach(cleanup);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactAccessPage />
    </QueryClientProvider>,
  );
}

describe('Contact Access tab', () => {
  it('AC-AM-7 renders What the chatbot answers with role chip and override badge', () => {
    renderPage();
    expect(screen.getByText('What the chatbot answers')).toBeTruthy();
    expect(screen.getAllByText('Purchasing').length).toBeGreaterThan(0);
    expect(screen.getByText('added here')).toBeTruthy();
  });

  it('AC-AM-7 no longer renders the Access Agents grid or the Field reveals switches', () => {
    renderPage();
    expect(screen.queryByText('Access Agents')).toBeNull();
    expect(screen.queryByText('Field reveals')).toBeNull();
  });
});
