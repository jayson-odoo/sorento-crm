import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ComplaintSettingsPage from './page';

// --- mocks ---
const mockSettings = { complaintDoDeliveredNotifyTiers: '1,2' };
vi.mock('../components/settings-context', () => ({
  useSettings: () => ({ settings: mockSettings, roles: [] }),
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));
vi.mock('sonner', () => ({ toast: { custom: vi.fn() } }));

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

describe('ComplaintSettingsPage', () => {
  beforeEach(() => {
    apiFetch.mockReset();
    mockSettings.complaintDoDeliveredNotifyTiers = '1,2';
  });

  it('reflects the saved tiers: Tier 1 + 2 checked, Tier 3 not', () => {
    wrap(<ComplaintSettingsPage />);
    expect(screen.getByLabelText('Tier 1').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByLabelText('Tier 2').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByLabelText('Tier 3').getAttribute('aria-checked')).toBe('false');
  });

  it('saves the selected tiers as a snake_case comma string', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    wrap(<ComplaintSettingsPage />);
    // turn Tier 2 off, Tier 3 on -> expect "1,3"
    fireEvent.click(screen.getByLabelText('Tier 2'));
    fireEvent.click(screen.getByLabelText('Tier 3'));
    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    const [url, opts] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/user-management/settings/general');
    expect(JSON.parse(opts.body)).toEqual({ complaint_do_delivered_notify_tiers: '1,3' });
  });

  it('warns when no tier is selected', () => {
    wrap(<ComplaintSettingsPage />);
    fireEvent.click(screen.getByLabelText('Tier 1'));
    fireEvent.click(screen.getByLabelText('Tier 2'));
    expect(screen.getByText(/no one will be notified/i)).toBeInTheDocument();
  });
});
