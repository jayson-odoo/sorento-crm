/**
 * M5-06 - the MCP tools catalog renders on DataGrid instead of a raw
 * `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const TOOLS = [
  { id: 't-1', tool_name: 'get_orders', module_key: 'order_management', description: 'List orders.' },
  { id: 't-2', tool_name: 'get_stock', module_key: 'inventory', description: null },
];

vi.mock('../hooks/useMcpAdmin', () => ({
  useMcpToolsCatalog: () => ({ data: TOOLS, isLoading: false }),
}));

import { McpToolsList } from './McpToolsList';

describe('McpToolsList - DataGrid', () => {
  it('renders the column headers and a real cell value for each tool', () => {
    render(<McpToolsList />);

    expect(screen.getByText('Tool')).toBeInTheDocument();
    expect(screen.getByText('Module')).toBeInTheDocument();
    expect(screen.getByText('Description')).toBeInTheDocument();

    expect(screen.getByText('get_orders')).toBeInTheDocument();
    expect(screen.getByText('get_stock')).toBeInTheDocument();
    expect(screen.getByText('order_management')).toBeInTheDocument();
    expect(screen.getByText('List orders.')).toBeInTheDocument();
  });
});
