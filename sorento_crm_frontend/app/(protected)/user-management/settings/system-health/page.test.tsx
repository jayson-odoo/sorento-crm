import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SystemHealthSettingsPage from './page';

// --- settings + roles context mock ------------------------------------------
type MockSettings = {
  healthDigestEnabled: boolean;
  healthAlertsEnabled: boolean;
  healthNotifyRoleIds: string[];
  healthIntegrationFailThreshold: number;
  healthAuditVolumeFloor: number;
};

const mockSettings: MockSettings = {
  healthDigestEnabled: true,
  healthAlertsEnabled: false,
  healthNotifyRoleIds: ['role-admin'],
  healthIntegrationFailThreshold: 10,
  healthAuditVolumeFloor: 5,
};

const mockRoles = [
  { id: 'role-admin', name: 'Administrator' },
  { id: 'role-ops', name: 'Operations' },
];

vi.mock('../components/settings-context', () => ({
  useSettings: () => ({ settings: mockSettings, roles: mockRoles }),
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));
vi.mock('@/lib/api-client', () => ({
  extractApiError: vi.fn(async () => 'Failed to save'),
}));
vi.mock('sonner', () => ({ toast: { custom: vi.fn() } }));

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

function resetSettings() {
  mockSettings.healthDigestEnabled = true;
  mockSettings.healthAlertsEnabled = false;
  mockSettings.healthNotifyRoleIds = ['role-admin'];
  mockSettings.healthIntegrationFailThreshold = 10;
  mockSettings.healthAuditVolumeFloor = 5;
}

describe('SystemHealthSettingsPage', () => {
  beforeEach(() => {
    apiFetch.mockReset();
    resetSettings();
  });

  it('seeds both toggles, the role multi-select and the two number inputs from settings', () => {
    wrap(<SystemHealthSettingsPage />);

    expect(screen.getByTestId('health-digest-enabled').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('health-alerts-enabled').getAttribute('aria-checked')).toBe('false');
    // selected role rendered as a human-readable badge (no raw UUID)
    expect(screen.getByText('Administrator')).toBeInTheDocument();
    expect(screen.queryByText('role-admin')).not.toBeInTheDocument();
    // number inputs seeded
    expect((screen.getByTestId('health-integration-fail-threshold') as HTMLInputElement).value).toBe(
      '10',
    );
    expect((screen.getByTestId('health-audit-volume-floor') as HTMLInputElement).value).toBe('5');
  });

  it('saves snake_case keys with the current values', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    wrap(<SystemHealthSettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    const [url, opts] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/user-management/settings/general');
    expect(opts.method).toBe('POST');
    expect(JSON.parse(opts.body)).toEqual({
      health_digest_enabled: true,
      health_alerts_enabled: false,
      health_notify_role_ids: ['role-admin'],
      health_integration_fail_threshold: 10,
      health_audit_volume_floor: 5,
    });
  });

  it('clamps a blank threshold back to the seeded value on save (non-negative int fallback)', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    wrap(<SystemHealthSettingsPage />);

    fireEvent.change(screen.getByTestId('health-integration-fail-threshold'), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    const body = JSON.parse(apiFetch.mock.calls[0][1].body);
    // blank -> NaN -> falls back to the seeded 10
    expect(body.health_integration_fail_threshold).toBe(10);
  });

  it('clamps a negative audit floor back to the seeded value on save', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    wrap(<SystemHealthSettingsPage />);

    fireEvent.change(screen.getByTestId('health-audit-volume-floor'), {
      target: { value: '-4' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    const body = JSON.parse(apiFetch.mock.calls[0][1].body);
    // negative -> falls back to the seeded 5
    expect(body.health_audit_volume_floor).toBe(5);
  });

  it('persists a valid edited integer value', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    wrap(<SystemHealthSettingsPage />);

    fireEvent.change(screen.getByTestId('health-integration-fail-threshold'), {
      target: { value: '25' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    const body = JSON.parse(apiFetch.mock.calls[0][1].body);
    expect(body.health_integration_fail_threshold).toBe(25);
  });

  it('warns about no recipients when a channel is on but no roles are selected', () => {
    mockSettings.healthNotifyRoleIds = [];
    wrap(<SystemHealthSettingsPage />);
    expect(
      screen.getByText(/no roles selected/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/fall back to superadmin and admin users/i),
    ).toBeInTheDocument();
  });

  it('does not warn when notifications are on and at least one role is selected', () => {
    wrap(<SystemHealthSettingsPage />);
    expect(screen.queryByText(/no roles selected/i)).not.toBeInTheDocument();
  });
});
