/**
 * UI v2 phase 0, slice S3 (red first). UAC B-7, B-8, B-9.
 *
 * EXPORT CONTRACT (modules do not exist yet):
 *   components/v2/version/UiVersionProvider.tsx : UiVersionProvider({ children })
 *     Reads the version ONCE from the existing /me profile query (hooks/useAccountProfileForHeader, react-query key
 *     ['account-profile']): fields `ui_version` (effective) and `ui_v2_available`. No second fetch. A missing
 *     field, a non-ok answer or a thrown fetch means v1 and unavailable. Sets `data-ui="v2"` on <html> while the
 *     effective version is v2 and removes the attribute otherwise.
 *   components/v2/version/useUiVersion.ts : useUiVersion(): {
 *       uiVersion: 'v1' | 'v2';        // 'v1' while loading
 *       uiV2Available: boolean;
 *       isLoading: boolean;            // true until /me has answered, failed or been answered null
 *       setUiVersion(next: 'v1' | 'v2'): Promise<boolean>;
 *     }
 *     setUiVersion does PUT /api/v1/user-management/users/me/ui-version {"ui_version": next} via apiFetch. On ok it
 *     updates the shared profile cache so the other version renders on the SAME url (no router.push/replace, no
 *     reload) and resolves true. On a non-ok answer or a throw it keeps the version, calls sonner `toast.error`
 *     with a message containing "could not switch", and resolves false.
 *   components/v2/version/VersionSwitchItem.tsx : VersionSwitchItem() - a plain <button role="menuitem"> (so it
 *     renders inside or outside a Radix menu) for the avatar menu. Renders nothing when uiV2Available is false;
 *     "Switch to the new version" in v1; "Switch to the previous version" in v2; click calls setUiVersion(other).
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Owner' } }, status: 'authenticated' }),
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

const push = vi.fn();
const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace, refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

const toastError = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a), success: vi.fn() } }));

import { UiVersionProvider } from './UiVersionProvider';
import { useUiVersion } from './useUiVersion';
import { VersionSwitchItem } from './VersionSwitchItem';

const PUT_URL = '/api/v1/user-management/users/me/ui-version';

let server: Record<string, unknown>;
let putStatus: number;

function profile(extra: Record<string, unknown>) {
  return { name: 'Owner', email: 'o@example.com', salesperson: null, ...extra };
}

function installFetch() {
  apiFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    if (String(url).includes(PUT_URL)) {
      if (putStatus >= 400) return { ok: false, status: putStatus, json: async () => ({ detail: 'nope' }) };
      server = { ...server, ui_version: JSON.parse(String(init?.body)).ui_version };
      return { ok: true, status: 200, json: async () => ({ ui_version: server.ui_version }) };
    }
    return { ok: true, status: 200, json: async () => server };
  });
}

function Probe() {
  const v = useUiVersion();
  return <div data-testid="probe">{v.isLoading ? 'loading' : `${v.uiVersion}|${v.uiV2Available}`}</div>;
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryDelay: 1 } } });
  return render(
    <QueryClientProvider client={client}>
      <UiVersionProvider>
        <Probe />
        <VersionSwitchItem />
      </UiVersionProvider>
    </QueryClientProvider>,
  );
}

const settled = () => waitFor(() => expect(screen.getByTestId('probe').textContent).not.toBe('loading'));

beforeEach(() => {
  vi.clearAllMocks();
  putStatus = 200;
  server = profile({ ui_version: 'v1', ui_v2_available: true });
  installFetch();
  document.documentElement.removeAttribute('data-ui');
  window.history.pushState({}, '', '/project-sales/order-inquiries?status=open&page=2');
});

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute('data-ui');
});

describe('B-7 avatar menu item', () => {
  it('is hidden when v2 is not available', async () => {
    server = profile({ ui_version: 'v1', ui_v2_available: false });
    mount();
    await settled();
    expect(screen.queryByText(/switch to the/i)).toBeNull();
  });

  it('says "Switch to the new version" in v1', async () => {
    mount();
    await settled();
    expect(screen.getByText('Switch to the new version')).toBeInTheDocument();
  });

  it('says "Switch to the previous version" in v2', async () => {
    server = profile({ ui_version: 'v2', ui_v2_available: true });
    mount();
    await settled();
    expect(screen.getByText('Switch to the previous version')).toBeInTheDocument();
  });
});

describe('B-8 switching', () => {
  it('PUTs, flips the version and keeps path and query without navigating', async () => {
    mount();
    await settled();
    fireEvent.click(screen.getByText('Switch to the new version'));
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('v2|true'));

    const put = apiFetch.mock.calls.find(([u]) => String(u).includes(PUT_URL));
    expect(put).toBeTruthy();
    expect(put![1].method).toBe('PUT');
    expect(JSON.parse(put![1].body)).toEqual({ ui_version: 'v2' });
    expect(window.location.pathname + window.location.search).toBe('/project-sales/order-inquiries?status=open&page=2');
    expect(push).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByText('Switch to the previous version')).toBeInTheDocument();
  });

  it('switching back sends v1', async () => {
    server = profile({ ui_version: 'v2', ui_v2_available: true });
    mount();
    await settled();
    fireEvent.click(screen.getByText('Switch to the previous version'));
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('v1|true'));
    const put = apiFetch.mock.calls.find(([u]) => String(u).includes(PUT_URL));
    expect(JSON.parse(put![1].body)).toEqual({ ui_version: 'v1' });
  });

  it('a failed PUT keeps the version and toasts that it could not switch', async () => {
    putStatus = 500;
    mount();
    await settled();
    fireEvent.click(screen.getByText('Switch to the new version'));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(String(toastError.mock.calls[0][0]).toLowerCase()).toContain('could not switch');
    expect(screen.getByTestId('probe').textContent).toBe('v1|true');
    expect(document.documentElement.hasAttribute('data-ui')).toBe(false);
  });

  it('a thrown PUT also keeps the version and toasts', async () => {
    apiFetch.mockImplementation(async (url: string) => {
      if (String(url).includes(PUT_URL)) throw new Error('network');
      return { ok: true, status: 200, json: async () => server };
    });
    mount();
    await settled();
    fireEvent.click(screen.getByText('Switch to the new version'));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(screen.getByTestId('probe').textContent).toBe('v1|true');
  });
});

describe('B-9 data-ui on <html>', () => {
  it('is "v2" only in v2', async () => {
    server = profile({ ui_version: 'v2', ui_v2_available: true });
    mount();
    await settled();
    await waitFor(() => expect(document.documentElement.getAttribute('data-ui')).toBe('v2'));
  });

  it('is set after a switch to v2 and removed after a switch back', async () => {
    mount();
    await settled();
    expect(document.documentElement.hasAttribute('data-ui')).toBe(false);
    fireEvent.click(screen.getByText('Switch to the new version'));
    await waitFor(() => expect(document.documentElement.getAttribute('data-ui')).toBe('v2'));
    fireEvent.click(screen.getByText('Switch to the previous version'));
    await waitFor(() => expect(document.documentElement.hasAttribute('data-ui')).toBe(false));
  });

  it('is absent in v1', async () => {
    mount();
    await settled();
    expect(document.documentElement.hasAttribute('data-ui')).toBe(false);
  });

  it('is absent and v1 when /me answers not ok', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    mount();
    await settled();
    expect(screen.getByTestId('probe').textContent).toBe('v1|false');
    expect(document.documentElement.hasAttribute('data-ui')).toBe(false);
  });

  it('is absent and v1 when /me throws', async () => {
    apiFetch.mockRejectedValue(new Error('network'));
    mount();
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('v1|false'), { timeout: 5000 });
    expect(document.documentElement.hasAttribute('data-ui')).toBe(false);
  });

  it('is absent and v1 when the profile has no version field', async () => {
    server = profile({});
    mount();
    await settled();
    expect(screen.getByTestId('probe').textContent).toBe('v1|false');
    expect(document.documentElement.hasAttribute('data-ui')).toBe(false);
  });

  it('reports loading, and v1 attribute-free, until /me answers', () => {
    apiFetch.mockReturnValue(new Promise(() => {}));
    mount();
    expect(screen.getByTestId('probe').textContent).toBe('loading');
    expect(document.documentElement.hasAttribute('data-ui')).toBe(false);
  });
});
