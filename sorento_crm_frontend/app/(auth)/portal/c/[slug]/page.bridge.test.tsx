/**
 * SIGNIN-2FA-NOT-ROLE AC-7 / AC-8 / AC-9: `/portal/c/<slug>` uses the CRM-session bridge.
 *
 * - AC-7: no device portal token + a NextAuth session -> `openPortalFromCrm(slug)` once; on a
 *   result the portal token + slug are stored and the landing renders; no verify redirect and
 *   no request-otp call.
 * - AC-8: no NextAuth session, or a bridge refusal / failure -> today's redirect to verify.
 * - AC-9: a device token for a DIFFERENT slug is cleared first ("slug wins"), then AC-7/AC-8.
 * - A device token for the SAME slug: no bridge call, the landing renders (unchanged).
 *
 * `openPortalFromCrm(slug: string): Promise<{ token: string; expires_at: string } | null>` is a
 * new export of `app/(auth)/portal/lib/portal-client.ts`; it is added in the mock factory so this
 * file fails on behaviour, not on an import.
 *
 * Fix round 1 R1 (nothing hangs): the page does NOT ask next-auth `getSession` (it can hang);
 * with no device token it calls `openPortalFromCrm(slug)` straight away, and a null answer (no
 * CRM session, refusal, failure) is the verify redirect. R4: one bridge call under StrictMode.
 *
 * Contract: documentation/plans/identity/signin-2fa-not-role-14nov-acceptance-criteria.md
 */
import React, { StrictMode, Suspense } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';

const router = { replace: vi.fn(), push: vi.fn() };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(window.location.search),
  usePathname: () => window.location.pathname,
}));

const getSessionMock = vi.fn();
vi.mock('next-auth/react', () => ({
  signIn: vi.fn(),
  signOut: vi.fn(),
  getSession: (...args: unknown[]) => getSessionMock(...args),
  useSession: () => ({ data: null, status: 'unauthenticated' }),
}));

vi.mock('../../components/PortalLanding', () => ({
  PortalLanding: ({ slug }: { slug?: string }) => <div data-testid="portal-landing">{slug}</div>,
}));

const bridgeMock = vi.fn();
const requestOtpMock = vi.fn();
vi.mock('../../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../lib/portal-client')>();
  return {
    ...original,
    openPortalFromCrm: (...args: unknown[]) => bridgeMock(...args),
    requestOtp: (...args: unknown[]) => requestOtpMock(...args),
  };
});

import PortalSlugPage from './page';
import { readPortalToken } from '../../lib/portal-client';
import { readPortalSlug } from '../../lib/portal-paths';

const SLUG = 'SLUG123456';
const OTHER_SLUG = 'OTHERSLUG9';
const TOKEN_KEY = 'sorento.portalToken';
const SLUG_KEY = 'sorento.portalSlug';
const BRIDGED = { token: 'BRIDGE-TOKEN', expires_at: '2026-12-14T00:00:00' };
const CRM_SESSION = { user: { id: 'u1', name: 'Test Salesperson A' }, apiToken: 'crm-session' };

async function renderPage(slug = SLUG, opts: { strict?: boolean } = {}) {
  const tree = (
    <Suspense fallback={null}>
      <PortalSlugPage params={Promise.resolve({ slug })} />
    </Suspense>
  );
  // React 19 `use(params)`: render inside act so the resolved params promise un-suspends.
  await act(async () => {
    render(opts.strict ? <StrictMode>{tree}</StrictMode> : tree);
  });
}

function verifyRedirects(): string[] {
  return router.replace.mock.calls
    .map((c) => String(c[0]))
    .filter((p) => p.includes('/verify'));
}

/** Let the mount effect and any awaited bridge/session promise settle. */
async function settle() {
  await new Promise((r) => setTimeout(r, 100));
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', `/portal/c/${SLUG}`);
  getSessionMock.mockResolvedValue(null);
  bridgeMock.mockResolvedValue(null);
});

describe('AC-7: no device token + a CRM session opens the portal through the bridge', () => {
  it('calls the bridge once with the slug, stores token + slug, renders the landing, no verify', async () => {
    getSessionMock.mockResolvedValue(CRM_SESSION);
    bridgeMock.mockResolvedValue(BRIDGED);

    await renderPage();

    expect(await screen.findByTestId('portal-landing')).toBeInTheDocument();
    expect(bridgeMock).toHaveBeenCalledTimes(1);
    expect(bridgeMock).toHaveBeenCalledWith(SLUG);
    expect(readPortalToken()).toBe(BRIDGED.token);
    expect(readPortalSlug()).toBe(SLUG);
    await settle();
    expect(verifyRedirects()).toEqual([]);
    expect(requestOtpMock).not.toHaveBeenCalled();
    expect(bridgeMock).toHaveBeenCalledTimes(1);
    // R1: next-auth getSession is never awaited on this path (it can hang).
    expect(getSessionMock).not.toHaveBeenCalled();
  });

  it('R1: a getSession that never resolves does not hold the page: the bridge still opens it', async () => {
    getSessionMock.mockImplementation(() => new Promise(() => {}));
    bridgeMock.mockResolvedValue(BRIDGED);

    await renderPage();

    expect(await screen.findByTestId('portal-landing')).toBeInTheDocument();
    expect(bridgeMock).toHaveBeenCalledTimes(1);
    expect(readPortalToken()).toBe(BRIDGED.token);
  });

  it('R4: under React StrictMode the bridge is called exactly once', async () => {
    bridgeMock.mockResolvedValue(BRIDGED);
    // A live CRM session either way, so this isolates the StrictMode double effect from R1.
    getSessionMock.mockResolvedValue(CRM_SESSION);

    await renderPage(SLUG, { strict: true });

    expect(await screen.findByTestId('portal-landing')).toBeInTheDocument();
    await settle();
    expect(bridgeMock).toHaveBeenCalledTimes(1);
    expect(bridgeMock).toHaveBeenCalledWith(SLUG);
    expect(verifyRedirects()).toEqual([]);
  });

  it('R4: under React StrictMode with a refusal, one bridge call and one verify redirect', async () => {
    bridgeMock.mockResolvedValue(null);
    // A live CRM session either way, so this isolates the StrictMode double effect from R1.
    getSessionMock.mockResolvedValue(CRM_SESSION);

    await renderPage(SLUG, { strict: true });

    await waitFor(() => expect(verifyRedirects().length).toBeGreaterThanOrEqual(1));
    await settle();
    expect(bridgeMock).toHaveBeenCalledTimes(1);
  });
});

describe('AC-8: no session, or the bridge refuses, keeps today\'s verify redirect', () => {
  it('no CRM session (the bridge answers null): one bridge call, redirect to verify', async () => {
    getSessionMock.mockResolvedValue(null);
    bridgeMock.mockResolvedValue(null);

    await renderPage();

    await waitFor(() => expect(verifyRedirects()).toHaveLength(1));
    expect(verifyRedirects()[0]).toContain(`/portal/c/${SLUG}/verify`);
    // R1: the bridge itself decides there is no CRM session; getSession is never asked.
    expect(getSessionMock).not.toHaveBeenCalled();
    expect(bridgeMock).toHaveBeenCalledTimes(1);
    expect(bridgeMock).toHaveBeenCalledWith(SLUG);
    expect(readPortalToken()).toBeNull();
    expect(screen.queryByTestId('portal-landing')).toBeNull();
  });

  it('a session but the bridge refuses (null): redirect to verify, nothing stored', async () => {
    getSessionMock.mockResolvedValue(CRM_SESSION);
    bridgeMock.mockResolvedValue(null);

    await renderPage();

    await waitFor(() => expect(bridgeMock).toHaveBeenCalledTimes(1));
    expect(bridgeMock).toHaveBeenCalledWith(SLUG);
    await waitFor(() => expect(verifyRedirects()).toHaveLength(1));
    expect(verifyRedirects()[0]).toContain(`/portal/c/${SLUG}/verify`);
    expect(readPortalToken()).toBeNull();
    expect(screen.queryByTestId('portal-landing')).toBeNull();
  });

  it('a session but the bridge throws: redirect to verify, nothing stored', async () => {
    getSessionMock.mockResolvedValue(CRM_SESSION);
    bridgeMock.mockRejectedValue(new Error('network down'));

    await renderPage();

    await waitFor(() => expect(bridgeMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(verifyRedirects()).toHaveLength(1));
    expect(readPortalToken()).toBeNull();
    expect(screen.queryByTestId('portal-landing')).toBeNull();
  });
});

describe('AC-9: a device token for a DIFFERENT slug is cleared, then the bridge rules apply', () => {
  beforeEach(() => {
    window.localStorage.setItem(TOKEN_KEY, 'OLD-OTHER-TOKEN');
    window.localStorage.setItem(SLUG_KEY, OTHER_SLUG);
  });

  it('with a session and a bridge result: old token gone, new token + slug stored, landing renders', async () => {
    getSessionMock.mockResolvedValue(CRM_SESSION);
    bridgeMock.mockResolvedValue(BRIDGED);

    await renderPage();

    expect(await screen.findByTestId('portal-landing')).toBeInTheDocument();
    expect(bridgeMock).toHaveBeenCalledTimes(1);
    expect(bridgeMock).toHaveBeenCalledWith(SLUG);
    expect(readPortalToken()).toBe(BRIDGED.token);
    expect(readPortalSlug()).toBe(SLUG);
    await settle();
    expect(verifyRedirects()).toEqual([]);
  });

  it('with no CRM session (bridge null): old token and slug cleared, one bridge call, redirect to verify', async () => {
    getSessionMock.mockResolvedValue(null);
    bridgeMock.mockResolvedValue(null);

    await renderPage();

    await waitFor(() => expect(verifyRedirects()).toHaveLength(1));
    expect(getSessionMock).not.toHaveBeenCalled();
    expect(bridgeMock).toHaveBeenCalledTimes(1);
    expect(readPortalToken()).toBeNull();
    expect(window.localStorage.getItem(SLUG_KEY)).not.toBe(OTHER_SLUG);
  });

  it('with a session but a bridge refusal: old token cleared, redirect to verify', async () => {
    getSessionMock.mockResolvedValue(CRM_SESSION);
    bridgeMock.mockResolvedValue(null);

    await renderPage();

    await waitFor(() => expect(bridgeMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(verifyRedirects()).toHaveLength(1));
    expect(readPortalToken()).toBeNull();
    expect(window.localStorage.getItem(SLUG_KEY)).not.toBe(OTHER_SLUG);
  });
});

describe('a device token for the SAME slug: unchanged, no bridge', () => {
  it('renders the landing with no bridge call and no redirect', async () => {
    window.localStorage.setItem(TOKEN_KEY, 'DEVICE-TOKEN');
    window.localStorage.setItem(SLUG_KEY, SLUG);
    getSessionMock.mockResolvedValue(CRM_SESSION);
    bridgeMock.mockResolvedValue(BRIDGED);

    await renderPage();

    expect(await screen.findByTestId('portal-landing')).toBeInTheDocument();
    await settle();
    expect(bridgeMock).not.toHaveBeenCalled();
    expect(readPortalToken()).toBe('DEVICE-TOKEN');
    expect(verifyRedirects()).toEqual([]);
  });
});
