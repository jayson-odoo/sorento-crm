/**
 * Access model S6, mock v8 (AC-AM-1, AC-AM-2, AC-AM-3, AC-AM-7, AC-AM-23). Red test: page.tsx absent.
 * Hooks (hooks/useChatbotAccess.ts): useChatbotRegistry, useChatbotRole(id), useSetRoleGrants(id)
 * -> { mutate({domains, fields}) }, useUpdateChatbotRole(id), useDeleteChatbotRole,
 * useChatbotRoleContacts(id) -> { data: [{ id, name }] }.
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
const dom = (name: string, label: string, group: string) => ({
  name, label, group, supported: true, access_section: null, escalation_agent_code: null, escalation_team_code: null, fields: [],
});
vi.mock('@/hooks/useChatbotAccess', () => ({
  useChatbotRegistry: () => ({
    data: { domains: [dom('master_products', 'Product details', 'Products and marketing'), dom('portal_link', 'Their request portal link', 'Products and marketing'), dom('forms', 'Forms', 'Products and marketing')] },
    isLoading: false,
    isError: false,
  }),
  useChatbotRole: () => ({
    data: { id: 'r1', code: 'purchasing', name: 'Purchasing', description: '', audience_tier: 'office', sees_all_customers: true, domains: ['master_products'], fields: [], contact_count: 1 },
    isLoading: false,
    isError: false,
  }),
  useChatbotRoleContacts: () => ({ data: [{ id: 'c1', name: 'Sorento - Jereen' }], isLoading: false, isError: false }),
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

describe('Chatbot role page (v8)', () => {
  it('AC-AM-1 shows Name, Tier and the customers radio from the role', () => {
    renderPage();
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('Purchasing');
    expect(screen.getByText('Tier')).toBeTruthy();
    expect(screen.getByText('Office')).toBeTruthy();
    expect((screen.getByRole('radio', { name: /All customers/ }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole('radio', { name: /Only the customers linked/ }) as HTMLInputElement).checked).toBe(false);
  });

  it('AC-AM-7 shows switches in role mode with the saved state', () => {
    renderPage();
    expect(screen.getByRole('switch', { name: 'Product details' }).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByRole('switch', { name: 'Forms' }).getAttribute('aria-checked')).toBe('false');
    expect(screen.queryByText(/Reset to role/)).toBeNull();
  });

  it('AC-AM-4 lists the contacts with this role and has a Delete button', () => {
    renderPage();
    expect(screen.getByText('Sorento - Jereen')).toBeTruthy();
    expect(screen.getByRole('button', { name: /^Delete/ })).toBeTruthy();
  });

  it('AC-AM-2 Save (2) after two switches and one setRoleGrants with the full set', () => {
    renderPage();
    fireEvent.click(screen.getByRole('switch', { name: 'Their request portal link' }));
    fireEvent.click(screen.getByRole('switch', { name: 'Forms' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save (2)' }));
    expect(mutate).toHaveBeenCalledTimes(1);
    const p = mutate.mock.calls[0][0] as { domains: string[]; fields: string[] };
    expect([...p.domains].sort()).toEqual(['forms', 'master_products', 'portal_link']);
    expect(p.fields).toEqual([]);
  });
});
