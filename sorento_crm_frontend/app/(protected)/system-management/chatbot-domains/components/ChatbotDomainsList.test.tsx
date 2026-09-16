/**
 * AC-1510 (chatbot-turn-rearch, S1): the Chatbot Domains DataGrid - column headers,
 * loading / empty / error / data states. Mirrors `McpToolsList.test.tsx` /
 * `PromptsList.test.tsx`'s convention (mock the data hook directly, no QueryClient
 * needed since the hook itself never reaches react-query in this test).
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import type { ChatbotDomain } from '../types/chatbotDomain.types';

const useChatbotDomainsQuery = vi.fn();
const useHasPermission = vi.fn();

vi.mock('../hooks/useChatbotDomains', () => ({
  useChatbotDomainsQuery: () => useChatbotDomainsQuery(),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => useHasPermission(slug),
}));
// The row-click modal is exercised by ChatbotDomainModal.test.tsx; stub it here so
// this file stays focused on the grid itself.
vi.mock('./ChatbotDomainModal', () => ({
  default: () => null,
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import ChatbotDomainsList from './ChatbotDomainsList';

const DOMAIN: ChatbotDomain = {
  id: 'd-1',
  name: 'incoming',
  label: 'Incoming stock',
  intents: ['check_incoming'],
  tools: ['crm_incoming_stock_list'],
  primary_tool: 'crm_incoming_stock_list',
  escalation_team_code: 'warehouse',
  switch_words: ['incoming', 'arrival'],
  narrowing: { product: 'must_narrow_one' },
  takes_date_filter: true,
  reveal_key: null,
  supported: true,
  ladder: ['stock'],
  updated_at: '2026-09-01T09:00:00',
};

beforeEach(() => {
  useChatbotDomainsQuery.mockReset();
  useHasPermission.mockReset();
  useHasPermission.mockReturnValue(true);
});
afterEach(() => cleanup());

describe('ChatbotDomainsList - AC-1510', () => {
  it('renders the column headers and a real cell value per row (data state)', () => {
    useChatbotDomainsQuery.mockReturnValue({ data: [DOMAIN], isLoading: false, isError: false });
    render(<ChatbotDomainsList />);

    expect(screen.getByText('Domain')).toBeInTheDocument();
    expect(screen.getByText('Label')).toBeInTheDocument();
    expect(screen.getByText('Tools')).toBeInTheDocument();
    expect(screen.getByText('Escalation team')).toBeInTheDocument();
    expect(screen.getByText('Switch words')).toBeInTheDocument();
    expect(screen.getByText('Narrowing')).toBeInTheDocument();
    expect(screen.getByText('Date filter')).toBeInTheDocument();
    expect(screen.getByText('Supported')).toBeInTheDocument();
    expect(screen.getByText('Updated')).toBeInTheDocument();

    expect(screen.getByText('incoming')).toBeInTheDocument();
    expect(screen.getByText('Incoming stock')).toBeInTheDocument();
    expect(screen.getByText('Warehouse')).toBeInTheDocument();
  });

  it('renders without throwing while loading (data undefined, isLoading true)', () => {
    useChatbotDomainsQuery.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<ChatbotDomainsList />);
    // The grid renders its own skeleton under jsdom (DataGrid depends on layout
    // measurement absent there, same limitation PromotionsList.test.tsx notes) - the
    // header row is still real DOM and is the stable loading-state assertion.
    expect(screen.getByText('Domain')).toBeInTheDocument();
  });

  it('renders the empty state with an Add domain action for a manager', () => {
    useChatbotDomainsQuery.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<ChatbotDomainsList />);
    // Both the toolbar's primary action and the grid's own empty-state placeholder
    // render an "Add domain" button on a genuinely empty page - at least one is the
    // stable assertion (this file targets AC-1510's own contract, not DataGrid's
    // internal empty-state markup).
    expect(screen.getAllByRole('button', { name: /Add domain/i }).length).toBeGreaterThan(0);
  });

  it('hides Add domain from a user without chatbot_config.manage', () => {
    useHasPermission.mockReturnValue(false);
    useChatbotDomainsQuery.mockReturnValue({ data: [DOMAIN], isLoading: false, isError: false });
    render(<ChatbotDomainsList />);
    expect(screen.queryByRole('button', { name: /Add domain/i })).not.toBeInTheDocument();
  });

  it('renders the error state', () => {
    useChatbotDomainsQuery.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<ChatbotDomainsList />);
    expect(screen.getByText(/could not be loaded/i)).toBeInTheDocument();
  });
});
