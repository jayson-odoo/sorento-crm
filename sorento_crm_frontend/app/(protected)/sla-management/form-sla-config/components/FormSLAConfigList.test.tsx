/**
 * M5-06 - FormSLAConfigList's per-form-type stage table renders on DataGrid
 * (via PanelDataGrid) instead of a raw `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const CONFIGS = [
  {
    id: 'c-1',
    source_entity_type: 'stock_inquiry',
    stage_code: 'STAGE_1',
    policy_id: 'p-1',
    agent_code: 'AGENT_A',
    team_set_code: 'TEAM_A',
    start_event: 'submitted',
    respond_event: 'responded',
    resolve_event: 'resolved',
    next_config_id: null,
    advance_on_event: null,
    is_active: true,
    policy_code: 'POL-1',
    policy_name: 'Standard SLA',
    next_stage_code: null,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  },
  {
    id: 'c-2',
    source_entity_type: 'stock_inquiry',
    stage_code: 'STAGE_2',
    policy_id: 'p-2',
    agent_code: 'AGENT_B',
    team_set_code: null,
    start_event: 'escalated',
    respond_event: null,
    resolve_event: null,
    next_config_id: null,
    advance_on_event: null,
    is_active: false,
    policy_code: null,
    policy_name: null,
    next_stage_code: null,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  },
];

vi.mock('../../_shared/formSLAService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/formSLAService')>();
  return {
    ...actual,
    listFormSLAConfigs: vi.fn(async () => CONFIGS),
    deleteFormSLAConfig: vi.fn(async () => {}),
  };
});

import FormSLAConfigList from './FormSLAConfigList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FormSLAConfigList />
    </QueryClientProvider>,
  );
}

describe('FormSLAConfigList - DataGrid', () => {
  it('renders the stage columns and a real cell value for each stage', async () => {
    renderList();

    expect(await screen.findByText('Stage')).toBeInTheDocument();
    expect(screen.getByText('Policy')).toBeInTheDocument();
    expect(screen.getByText('Agent')).toBeInTheDocument();
    expect(screen.getByText('Team set')).toBeInTheDocument();

    expect(screen.getByText('STAGE_1')).toBeInTheDocument();
    expect(screen.getByText('STAGE_2')).toBeInTheDocument();
    expect(screen.getByText('Standard SLA')).toBeInTheDocument();
    expect(screen.getByText('(unnamed policy)')).toBeInTheDocument();
  });
});
