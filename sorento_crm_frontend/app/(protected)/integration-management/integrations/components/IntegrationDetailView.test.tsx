/**
 * RED tests for SR6 (issue #1077) - the Test button on IntegrationDetailView.
 *
 * Plan: documentation/plans/autocount/PLAN-foundryx-pull-connection-ui.md
 * UAC:  documentation/plans/autocount/foundryx-pull-connection-ui-acceptance-criteria.md
 * AC-FE-1 Test button only for type === 'autocount_esb'.
 * AC-FE-2 disabled + "Testing" while pending (no bare "Loading…").
 * AC-FE-3 success Badge "Connected" on ok, destructive Badge with the message on
 *         failure, inline (no toast/dialog), a new click replaces the old result.
 *
 * Nothing under test exists yet: IntegrationDetailView has no Test button today, so
 * every `findByRole('button', { name: /^test$/i })` below times out and fails - the
 * correct red. The seam this pins for the coder:
 *
 *   - `testIntegration(id: string)` in `../services/integrationService.ts`, calling
 *     `POST {BASE}/{id}/test` and resolving `{ ok, message, latency_ms }`.
 *   - `useTestIntegration()` in `../hooks/useIntegrations.ts`, a mutation wrapping it.
 *
 * The service is mocked at the module boundary (this file never hits the network);
 * `useTestIntegration` is left REAL so this also proves the hook is wired to the
 * button, not just that the service function exists.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { IntegrationDetailView } from './IntegrationDetailView';
import type { Integration } from '../types/integration.types';

const ESB_ID = 'int-esb-1';
const OTHER_ID = 'int-n8n-1';

const ESB_INTEGRATION: Integration = {
  id: ESB_ID,
  name: 'foundryx-esb',
  type: 'autocount_esb',
  status: 'ACTIVE',
  act_as_user_id: 'u-1',
  act_as_user_name: 'Integration: FoundryX ESB',
  config_json: { base_url: 'https://esb.foundryx.my' },
  has_credentials: true,
  is_active: true,
  last_used_at: null,
  last_error: null,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  keys: [],
};

const OTHER_INTEGRATION: Integration = {
  ...ESB_INTEGRATION,
  id: OTHER_ID,
  name: 'n8n',
  type: 'automation',
};

const h = vi.hoisted(() => ({
  push: vi.fn(),
  getIntegration: vi.fn(),
  testIntegration: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: h.push, back: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => `/integration-management/integrations/${ESB_ID}`,
}));

// The delete danger-zone (`watchFromMount: true`) polls this on mount - stubbed so
// the test never hits the network for a feature this file does not exercise.
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

vi.mock('@/lib/toast', () => {
  const noop = () => {};
  const toast = Object.assign(noop, {
    success: noop,
    error: noop,
    warning: noop,
    info: noop,
    message: noop,
    custom: noop,
    loading: noop,
    dismiss: noop,
  });
  return { toast, Toaster: () => null };
});

// Module-boundary mock (this file's data layer never hits the network). `testIntegration`
// is the new SR6 seam the coder adds to the real module - naming it here is the contract.
vi.mock('../services/integrationService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/integrationService')>()),
  getIntegration: (...args: unknown[]) => h.getIntegration(...args),
  issueKey: vi.fn(),
  rotateKey: vi.fn(),
  createIntegration: vi.fn(),
  updateIntegration: vi.fn(),
  testIntegration: (...args: unknown[]) => h.testIntegration(...args),
}));

function renderView(id: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <IntegrationDetailView id={id} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  h.getIntegration.mockImplementation(async (id: string) =>
    id === ESB_ID ? ESB_INTEGRATION : OTHER_INTEGRATION,
  );
});

describe('IntegrationDetailView - AC-FE-1 Test button visibility', () => {
  // One test, both branches: a "does NOT render" assertion is trivially true before
  // the button exists at all for ANY type, so pairing it with the positive branch in
  // the same test is what makes this red for the right reason today (no Test button
  // anywhere yet) rather than green by accident.
  it('shows a Test button only for an autocount_esb integration', async () => {
    renderView(ESB_ID);
    // The page header renders the integration name as an <h1> - the SAME string
    // also appears in the "Name" field below, so a bare findByText is ambiguous.
    expect(await screen.findByRole('heading', { name: 'foundryx-esb' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^test$/i })).toBeInTheDocument();

    cleanup();

    renderView(OTHER_ID);
    expect(await screen.findByRole('heading', { name: 'n8n' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^test$/i })).not.toBeInTheDocument();
  });
});

describe('IntegrationDetailView - AC-FE-2 pending state', () => {
  it('disables the button and reads "Testing" while the request is pending', async () => {
    let resolveTest: (value: { ok: boolean; message: string; latency_ms: number }) => void =
      () => {};
    h.testIntegration.mockReturnValue(
      new Promise((resolve) => {
        resolveTest = resolve;
      }),
    );

    renderView(ESB_ID);
    const button = await screen.findByRole('button', { name: /^test$/i });

    fireEvent.click(button);

    await waitFor(() => expect(button).toBeDisabled());
    // The shared loading convention, not a bare "Loading…" (AC-FE-2).
    expect(button.textContent ?? '').toMatch(/testing/i);
    expect((button.textContent ?? '').toLowerCase()).not.toBe('loading…');

    resolveTest({ ok: true, message: 'Connected', latency_ms: 42 });
    await waitFor(() => expect(button).not.toBeDisabled());
  });
});

describe('IntegrationDetailView - AC-FE-3 inline result, no toast/dialog', () => {
  it('shows a success Badge reading "Connected" on ok:true', async () => {
    h.testIntegration.mockResolvedValue({ ok: true, message: 'Connected', latency_ms: 42 });

    renderView(ESB_ID);
    fireEvent.click(await screen.findByRole('button', { name: /^test$/i }));

    const badgeText = await screen.findByText('Connected');
    expect(badgeText.closest('[data-slot="badge"]')?.className ?? '').toMatch(/success/);
    // Result is inline, never a dialog.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows a destructive Badge carrying the message on ok:false, replaced by the next click', async () => {
    h.testIntegration.mockResolvedValueOnce({
      ok: false,
      message: 'Key rejected',
      latency_ms: 10,
    });

    renderView(ESB_ID);
    fireEvent.click(await screen.findByRole('button', { name: /^test$/i }));

    const failBadge = await screen.findByText('Key rejected');
    expect(failBadge.closest('[data-slot="badge"]')?.className ?? '').toMatch(/destructive/);

    h.testIntegration.mockResolvedValueOnce({ ok: true, message: 'Connected', latency_ms: 12 });
    fireEvent.click(await screen.findByRole('button', { name: /^test$/i }));

    await screen.findByText('Connected');
    expect(screen.queryByText('Key rejected')).not.toBeInTheDocument();
  });
});
