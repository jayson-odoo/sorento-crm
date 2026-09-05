/**
 * Settings layout tab strip - the new "Chatbot" tab (AC-809, AC-810, issue #679).
 *
 * RED, written before `layout.tsx`'s `navRoutes` gains a `chatbot` entry. Today it
 * has ten tabs, one of them "Chatbot Media" (a DIFFERENT feature - per-contact
 * media allowances, `settings/chatbot-media`), and no plain "Chatbot" tab pointing
 * at `settings/chatbot` (the lane/switches screen this ticket adds). This test
 * fails today because that tab does not exist; it must not be satisfied by the
 * existing "Chatbot Media" tab, so the assertion requires an EXACT match.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/settings/chatbot',
  useRouter: () => ({ push: vi.fn() }),
}));

// `Container` reaches the app-wide settings-provider (`providers/settings-
// provider.tsx`, unrelated to the local `components/settings-context.tsx`), which
// this test does not otherwise supply. Same stub as
// `sla-management/kpi-dashboard/page.test.tsx`.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import Layout from './layout';

afterEach(() => cleanup());

function renderLayout() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  apiFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ settings: { id: 's1', name: 'Sorento' }, roles: [] }),
  });
  return render(
    <QueryClientProvider client={client}>
      <Layout>
        <div>child</div>
      </Layout>
    </QueryClientProvider>,
  );
}

describe('Settings tab strip', () => {
  it('lists a "Chatbot" tab distinct from the existing "Chatbot Media" tab', async () => {
    renderLayout();

    const chatbotTab = await screen.findByRole('tab', { name: 'Chatbot' });
    expect(chatbotTab).toBeInTheDocument();

    // Regression guard: the pre-existing, unrelated tab is still there under its
    // own, different name - this ticket must not rename or replace it.
    expect(screen.getByRole('tab', { name: 'Chatbot Media' })).toBeInTheDocument();
  });
});
