/**
 * M5-06 - the email event kill-switch table renders on DataGrid instead of a
 * raw `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const CONFIGS = [
  {
    event_key: 'order.created',
    display_name: 'Order created',
    description: 'Fires when a new order is placed.',
    enabled: true,
    rate_per_window_override: null,
    window_seconds_override: null,
    coalesce_window_seconds_override: null,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  },
  {
    event_key: 'order.cancelled',
    display_name: 'Order cancelled',
    description: null,
    enabled: false,
    rate_per_window_override: 5,
    window_seconds_override: 60,
    coalesce_window_seconds_override: null,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  },
];

const updateMut = { mutate: vi.fn(), isPending: false };

vi.mock('../hooks/useEmailEventConfigs', () => ({
  useEmailEventConfigs: () => ({ data: CONFIGS, isLoading: false }),
  useUpdateEmailEventConfig: () => updateMut,
}));

import EmailEventConfigsTable from './EmailEventConfigsTable';

describe('EmailEventConfigsTable - DataGrid', () => {
  it('renders the column headers and a real cell value for each event', () => {
    render(<EmailEventConfigsTable />);

    expect(screen.getByText('Event')).toBeInTheDocument();
    expect(screen.getByText('Enabled')).toBeInTheDocument();
    expect(screen.getByText('Rate / window override')).toBeInTheDocument();

    expect(screen.getByText('Order created')).toBeInTheDocument();
    expect(screen.getByText('Order cancelled')).toBeInTheDocument();
    expect(screen.getByText('order.created')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Save overrides' })).toHaveLength(2);
  });
});
