/**
 * UI v2 phase 0, slice S3 (red first). UAC B-11.
 *
 * EXPORT CONTRACT:
 *   components/v2/version/V2ErrorBoundary.tsx : V2ErrorBoundary({ children })  (React error boundary)
 *     On a thrown child it shows "This screen hit a problem." and a button "Open in the previous version".
 *     It reports once through lib/client-error-report `reportClientError(error, 'protected', { ui_version: 'v2' })`
 *     (the third argument is NEW: extra fields merged into the report body; the coder extends
 *     lib/client-error-report.ts and its test). The button PUTs
 *     /api/v1/user-management/users/me/ui-version {"ui_version":"v1"} through apiFetch, then reloads the same URL
 *     with window.location.reload(). It does not need UiVersionProvider (it calls apiFetch itself, because the
 *     provider may be what broke).
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

const reportClientError = vi.fn();
vi.mock('@/lib/client-error-report', () => ({
  reportClientError: (...a: unknown[]) => reportClientError(...a),
}));

import { V2ErrorBoundary } from './V2ErrorBoundary';

let reload: ReturnType<typeof vi.fn>;

function Boom(): React.ReactElement {
  throw new Error('v2 screen exploded');
}

beforeEach(() => {
  vi.clearAllMocks();
  reload = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, reload, pathname: '/inventory/stock-inquiries', search: '?q=1' },
  });
  apiFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('V2ErrorBoundary', () => {
  it('renders children untouched when nothing throws', () => {
    render(
      <V2ErrorBoundary>
        <p>fine</p>
      </V2ErrorBoundary>,
    );
    expect(screen.getByText('fine')).toBeInTheDocument();
    expect(reportClientError).not.toHaveBeenCalled();
  });

  it('shows the plain message and the way back', () => {
    render(
      <V2ErrorBoundary>
        <Boom />
      </V2ErrorBoundary>,
    );
    expect(screen.getByText('This screen hit a problem.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open in the previous version' })).toBeInTheDocument();
  });

  it('reports the error with ui_version v2', () => {
    render(
      <V2ErrorBoundary>
        <Boom />
      </V2ErrorBoundary>,
    );
    expect(reportClientError).toHaveBeenCalledTimes(1);
    const [err, boundary, extra] = reportClientError.mock.calls[0];
    expect((err as Error).message).toBe('v2 screen exploded');
    expect(boundary).toBe('protected');
    expect(extra).toEqual({ ui_version: 'v2' });
  });

  it('"Open in the previous version" PUTs v1 and reloads the same URL', async () => {
    render(
      <V2ErrorBoundary>
        <Boom />
      </V2ErrorBoundary>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Open in the previous version' }));
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    const put = apiFetch.mock.calls.find(([u]) => String(u).includes('/api/v1/user-management/users/me/ui-version'));
    expect(put).toBeTruthy();
    expect(put![1].method).toBe('PUT');
    expect(JSON.parse(put![1].body)).toEqual({ ui_version: 'v1' });
  });

  it('does not reload when the PUT fails (the user is never sent in a loop)', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    render(
      <V2ErrorBoundary>
        <Boom />
      </V2ErrorBoundary>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Open in the previous version' }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(reload).not.toHaveBeenCalled();
    expect(screen.getByText('This screen hit a problem.')).toBeInTheDocument();
  });
});
