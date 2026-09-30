/**
 * useAutocountPullAction - a click event handed to `onSelect` (HOTFIX-AUTOCOUNT-PULL-EVENT).
 *
 * Production, 30 Sep 2026: Products > Actions > Pull from AutoCount toasted "Converting
 * circular structure to JSON ... HTMLDivElement ... __reactFiber$". The toolbar calls a menu
 * item's `onClick` with the React click event, both lists wired `onClick: autocountPull.onSelect`
 * and PR #1383 gave `onSelect` an optional `scope`, so the event arrived as the scope, passed
 * the truthy check, and `startPull` ran `JSON.stringify` on it.
 *
 * Unlike the sibling test files this one mocks `@/lib/api`, NOT the service, so the real
 * `startPull` serialises the body and the assertion is on the bytes that would leave the
 * browser: `{ entity }` alone for a click event, `{ entity, scope }` for the dialog's scope.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const useHasPermission = vi.fn();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (...a: unknown[]) => useHasPermission(...a),
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: { error: (...a: unknown[]) => toastError(...a), success: vi.fn() },
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  isAutocountPullScope,
  useAutocountPullAction,
} from './useAutocountPull';

function ok(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function notFound(): Response {
  return {
    ok: false,
    status: 404,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail: 'No open pull' }),
    text: async () => '{"detail":"No open pull"}',
  } as unknown as Response;
}

/** The shape React hands a menu item's `onClick`: a class instance (not a plain object)
 *  whose `currentTarget` is a DOM node carrying the fiber back-reference that closes the
 *  cycle `JSON.stringify` tripped on in production. */
function fakeClickEvent(): unknown {
  const element = document.createElement('div') as HTMLDivElement &
    Record<string, unknown>;
  const fiber: Record<string, unknown> = { tag: 5 };
  fiber.stateNode = element;
  element['__reactFiber$abc123'] = fiber;
  class SyntheticBaseEvent {
    type = 'click';
    currentTarget = element;
    target = element;
    nativeEvent = { type: 'click' };
    preventDefault() {}
    stopPropagation() {}
  }
  return new SyntheticBaseEvent();
}

function postBodies(): unknown[] {
  return apiFetch.mock.calls
    .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)));
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  useHasPermission.mockReset();
  useHasPermission.mockReturnValue(true);
  apiFetch.mockReset();
  apiFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const { entity } = JSON.parse(String(init.body));
      return ok({ job_id: `job-${entity}`, entity, phase: 'building' });
    }
    if (url.includes('/pulls/current')) return notFound();
    throw new Error(`unexpected apiFetch ${url}`);
  });
  push.mockClear();
  toastError.mockClear();
});

describe('the fake event reproduces the production shape', () => {
  it('cannot be JSON-serialised (the cycle the toast named)', () => {
    expect(() => JSON.stringify(fakeClickEvent())).toThrow(/circular/i);
  });
});

describe('isAutocountPullScope', () => {
  it('accepts the plain scope object the Delivery Orders dialog passes', () => {
    expect(
      isAutocountPullScope({ fromDay: '2026-09-01', toDay: '2026-09-30' }),
    ).toBe(true);
    expect(isAutocountPullScope({ docNo: 'DO-0001' })).toBe(true);
    expect(isAutocountPullScope({})).toBe(true);
  });

  it('rejects a click event, a DOM element, and anything that is not a plain scope', () => {
    expect(isAutocountPullScope(fakeClickEvent())).toBe(false);
    expect(isAutocountPullScope(document.createElement('div'))).toBe(false);
    expect(isAutocountPullScope(null)).toBe(false);
    expect(isAutocountPullScope(undefined)).toBe(false);
    expect(isAutocountPullScope('2026-09-01')).toBe(false);
    expect(isAutocountPullScope({ fromDay: 1 })).toBe(false);
    expect(isAutocountPullScope({ fromDay: '2026-09-01', target: {} })).toBe(
      false,
    );
  });
});

describe('useAutocountPullAction.onSelect handed a click event (Products, Stock Balance)', () => {
  it.each(['products', 'stock_balances'] as const)(
    '%s: POSTs { entity } only, navigates to the new job, no error toast',
    async (entity) => {
      const { result } = renderHook(() => useAutocountPullAction(entity), {
        wrapper,
      });
      await waitFor(() => expect(result.current.visible).toBe(true));
      await waitFor(() =>
        expect(apiFetch).toHaveBeenCalledWith(
          expect.stringContaining('/pulls/current'),
        ),
      );

      await act(async () => {
        await result.current.onSelect(fakeClickEvent() as never);
      });

      expect(postBodies()).toEqual([{ entity }]);
      expect(push).toHaveBeenCalledWith(
        `/system-management/import-jobs/job-${entity}`,
      );
      expect(toastError).not.toHaveBeenCalled();
    },
  );
});

describe('useAutocountPullAction.onSelect with the Delivery Orders scope (PR #1383 path kept)', () => {
  it('POSTs { entity, scope } with the dialog window', async () => {
    const scope = { fromDay: '2026-09-01', toDay: '2026-09-30' };
    const { result } = renderHook(
      () => useAutocountPullAction('delivery_orders'),
      { wrapper },
    );
    await waitFor(() => expect(result.current.visible).toBe(true));

    await act(async () => {
      await result.current.onSelect(scope);
    });

    expect(postBodies()).toEqual([{ entity: 'delivery_orders', scope }]);
    expect(push).toHaveBeenCalledWith(
      '/system-management/import-jobs/job-delivery_orders',
    );
    expect(toastError).not.toHaveBeenCalled();
  });

  it('POSTs { entity } only when called with no scope (the 31-day default)', async () => {
    const { result } = renderHook(
      () => useAutocountPullAction('delivery_orders'),
      { wrapper },
    );
    await waitFor(() => expect(result.current.visible).toBe(true));

    await act(async () => {
      await result.current.onSelect();
    });

    expect(postBodies()).toEqual([{ entity: 'delivery_orders' }]);
  });
});
