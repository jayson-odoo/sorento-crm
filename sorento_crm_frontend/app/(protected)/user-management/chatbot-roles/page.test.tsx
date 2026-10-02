/**
 * Access model S6 (AC-AM-1, AC-AM-3). Red test: chatbot-roles/page.tsx and hooks/useChatbotAccess.ts
 * do not exist. Hook names pinned: useChatbotRoles() -> { data: Role[], isLoading, isError }.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ChatbotRolesPage from './page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({}),
  usePathname: () => '/user-management/chatbot-roles',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/hooks/useChatbotAccess', () => ({
  useChatbotRoles: () => ({
    data: [
      { id: 'r1', code: 'purchasing', name: 'Purchasing', description: 'Buying team', sees_all_customers: true, domains: ['inventory'], fields: [], contact_count: 5 },
      { id: 'r2', code: 'dealer', name: 'Dealer', description: '', sees_all_customers: false, domains: [], fields: [], contact_count: 0 },
    ],
    isLoading: false,
    isError: false,
  }),
  useCreateChatbotRole: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteChatbotRole: () => ({ mutate: vi.fn(), isPending: false }),
}));

afterEach(cleanup);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatbotRolesPage />
    </QueryClientProvider>,
  );
}

describe('Chatbot Roles list page', () => {
  it('AC-AM-1 renders a row per role with its contact count', () => {
    renderPage();
    expect(screen.getByText('Purchasing')).toBeTruthy();
    expect(screen.getByText('Dealer')).toBeTruthy();
    expect(screen.getByText('5')).toBeTruthy();
  });

  it('AC-AM-1 has an Add role button', () => {
    renderPage();
    expect(screen.getByRole('button', { name: /add role/i })).toBeTruthy();
  });
});
