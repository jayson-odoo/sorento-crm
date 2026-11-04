/**
 * CLIENT-ERROR-REPORT, crew pass on b51007ba: with Safari's website storage blocked
 * every `localStorage` access throws SecurityError, and the protected shell read it
 * unguarded (ImpersonationBanner), so every signed-in page showed "The app could not
 * start". The shell's real storage users render here with storage throwing; only
 * auth and the heavy sidebar layout are stubbed.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/procurement-management/stock-inquiries',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ status: 'authenticated', data: { user: { id: 'u-1' } } }),
  signOut: vi.fn(async () => undefined),
}));
vi.mock('@/hooks/useImpersonation', () => ({
  useImpersonation: () => ({
    hydrate: vi.fn(async () => null),
    session: null,
    stop: vi.fn(),
    stopping: false,
  }),
}));
vi.mock('../components/layouts/demo1/layout', async () => {
  const { ImpersonationBanner } = await import('@/components/impersonation/ImpersonationBanner');
  return {
    Demo1Layout: ({ children }: { children: React.ReactNode }) => (
      <div>
        <ImpersonationBanner />
        {children}
      </div>
    ),
  };
});

const blocked = () => {
  throw new DOMException('The operation is insecure.', 'SecurityError');
};
const real = {
  local: Object.getOwnPropertyDescriptor(window, 'localStorage')!,
  session: Object.getOwnPropertyDescriptor(window, 'sessionStorage')!,
};

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })));
  Object.defineProperty(window, 'localStorage', { configurable: true, get: blocked });
  Object.defineProperty(window, 'sessionStorage', { configurable: true, get: blocked });
});

afterEach(() => {
  Object.defineProperty(window, 'localStorage', real.local);
  Object.defineProperty(window, 'sessionStorage', real.session);
  vi.unstubAllGlobals();
});

describe('protected shell with website storage blocked (Safari)', () => {
  it('renders the page instead of throwing', async () => {
    const { default: ProtectedLayout } = await import('./layout');
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ProtectedLayout>Stock Inquiries page</ProtectedLayout>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Stock Inquiries page')).toBeTruthy();
  });
});
