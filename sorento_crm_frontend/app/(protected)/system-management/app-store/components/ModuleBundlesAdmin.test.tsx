/**
 * M5-06 - the module bundles admin table renders on DataGrid instead of a
 * raw `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

vi.mock('@/hooks/useTenantModules', () => ({
  TENANT_MODULES_QUERY_KEY: ['tenant-modules'],
  useTenantModules: () => ({ raw: { modules: [] } }),
}));

const BUNDLES = [
  { bundle_key: 'sales_stack', display_name: 'Sales Stack', module_keys: ['crm', 'orders'], sort_order: '001' },
  { bundle_key: 'ops_stack', display_name: 'Ops Stack', module_keys: ['inventory'], sort_order: null },
];

vi.mock('../services/moduleBundlesService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/moduleBundlesService')>();
  return {
    ...actual,
    fetchModuleBundles: vi.fn(async () => BUNDLES),
  };
});

import ModuleBundlesAdmin from './ModuleBundlesAdmin';

function renderAdmin() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ModuleBundlesAdmin />
    </QueryClientProvider>,
  );
}

describe('ModuleBundlesAdmin - DataGrid', () => {
  it('renders the bundle columns and a real cell value for each bundle', async () => {
    renderAdmin();

    expect(await screen.findByText('Key')).toBeInTheDocument();
    expect(screen.getByText('Display name')).toBeInTheDocument();
    expect(screen.getByText('Modules')).toBeInTheDocument();

    expect(screen.getByText('sales_stack')).toBeInTheDocument();
    expect(screen.getByText('ops_stack')).toBeInTheDocument();
    expect(screen.getByText('Sales Stack')).toBeInTheDocument();
  });
});
