/**
 * Access model S6 (AC-AM-2). Red test: chatbot-roles/[id]/page.tsx does not exist.
 * Hook names pinned (hooks/useChatbotAccess.ts):
 *   useChatbotRegistry() -> { data: {domains}, isLoading, isError }
 *   useChatbotRole(id)   -> { data: Role, isLoading, isError }
 *   useSetRoleGrants(id) -> { mutate({domains, fields}), isPending }
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatbotRolePage from './page';

const mutate = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useParams: () => ({ id: 'r1' }),
  usePathname: () => '/user-management/chatbot-roles/r1',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/hooks/useChatbotAccess', () => ({
  useChatbotRegistry: () => ({
    data: {
      domains: [
        { name: 'master_products', label: 'Product', supported: true, access_section: null, escalation_agent_code: null, escalation_team_code: null, fields: [] },
        { name: 'portal_link', label: 'Portal link', supported: true, access_section: null, escalation_agent_code: null, escalation_team_code: null, fields: [] },
        { name: 'forms', label: 'Forms', supported: true, access_section: null, escalation_agent_code: null, escalation_team_code: null, fields: [] },
      ],
    },
    isLoading: false,
    isError: false,
  }),
  useChatbotRole: () => ({
    data: { id: 'r1', code: 'purchasing', name: 'Purchasing', description: '', sees_all_customers: true, domains: ['master_products'], fields: [], contact_count: 5 },
    isLoading: false,
    isError: false,
  }),
  useSetRoleGrants: () => ({ mutate, isPending: false }),
  useUpdateChatbotRole: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteChatbotRole: () => ({ mutate: vi.fn(), isPending: false }),
}));

afterEach(() => {
  cleanup();
  mutate.mockReset();
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatbotRolePage />
    </QueryClientProvider>,
  );
}

describe('Chatbot role page', () => {
  it('AC-AM-2 shows the saved ticks and the tree headings', () => {
    renderPage();
    expect(screen.getByRole('checkbox', { name: 'Product' }).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByRole('checkbox', { name: 'Portal link' }).getAttribute('aria-checked')).toBe('false');
    expect(screen.getByText('Domains')).toBeTruthy();
  });

  it('AC-AM-2 Save shows (2) after two ticks and writes the full set once', () => {
    renderPage();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Portal link' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Forms' }));
    const save = screen.getByRole('button', { name: 'Save (2)' });
    fireEvent.click(save);
    expect(mutate).toHaveBeenCalledTimes(1);
    const payload = mutate.mock.calls[0][0] as { domains: string[]; fields: string[] };
    expect([...payload.domains].sort()).toEqual(['forms', 'master_products', 'portal_link']);
    expect(payload.fields).toEqual([]);
  });
});
