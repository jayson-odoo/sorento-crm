/**
 * The card reads the full settings blob, which is gated on
 * `user_management.settings.view` (Q2 of
 * documentation/plans/security/PLAN-user-management-read-gates.md), while the page
 * it sits on is gated on the independent `system.ai_assistant_settings.view`. A role
 * holding only the latter gets a 403 on the read.
 *
 * That is the case under test: the card must not fall back to DEFAULTS and then let
 * Save POST them to `/settings/general` (a write route with no permission
 * dependency), because that overwrites the real trace configuration with values
 * nobody ever saw.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import TraceSettingsCard from './TraceSettingsCard';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const SETTINGS_URL = '/api/user-management/settings/';

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    React.createElement(QueryClientProvider, { client }, React.createElement(TraceSettingsCard)),
  );
}

beforeEach(() => {
  apiFetch.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('TraceSettingsCard', () => {
  it('renders the saved values when the read succeeds', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        settings: {
          ai_assistant_role_split_enabled: true,
          ai_trace_ttl_days: 7,
          ai_trace_error_ttl_days: 45,
          ai_trace_max_payload_bytes: 4096,
        },
      }),
    } as unknown as Response);

    renderCard();

    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy());
    expect(apiFetch).toHaveBeenCalledWith(SETTINGS_URL);
    expect((screen.getByLabelText('Trace retention (days)') as HTMLInputElement).value).toBe('7');
    expect((screen.getByLabelText('Payload cap (bytes)') as HTMLInputElement).value).toBe('4096');
  });

  it('offers no Save when the read is denied, and says so', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 403 } as unknown as Response);

    renderCard();

    await waitFor(() => expect(screen.getByTestId('trace-settings-load-failed')).toBeTruthy());
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
    expect(screen.queryByLabelText('Trace retention (days)')).toBeNull();
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(apiFetch).not.toHaveBeenCalledWith(
      '/api/user-management/settings/general',
      expect.anything(),
    );
  });

  it('offers no Save when the read throws', async () => {
    apiFetch.mockRejectedValue(new Error('network down'));

    renderCard();

    await waitFor(() => expect(screen.getByTestId('trace-settings-load-failed')).toBeTruthy());
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
  });
});
