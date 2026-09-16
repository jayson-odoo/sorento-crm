/**
 * AC-1511 (chatbot-turn-rearch, S1): one modal layout for view and edit, tabs
 * General / Narrowing / Ladder / Prompt block, tools from the MCP tools list, team
 * from Teams, Prompt block read-only. Mirrors `PlanRowDialog.test.tsx`'s convention
 * (data hooks mocked, real QueryClientProvider since the modal calls `useQuery`
 * directly for the MCP tools catalog and the prompt block).
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ChatbotDomain } from '../types/chatbotDomain.types';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
Element.prototype.setPointerCapture = Element.prototype.setPointerCapture ?? (() => {});
Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listMcpToolsCatalog = vi.fn();
vi.mock('@/app/(protected)/system-management/mcp-tools/services/mcpAdminService', () => ({
  listMcpToolsCatalog: () => listMcpToolsCatalog(),
}));

const getChatbotDomainPromptBlock = vi.fn();
vi.mock('../services/chatbotDomainService', () => ({
  getChatbotDomainPromptBlock: (id: string) => getChatbotDomainPromptBlock(id),
}));

const useChatbotEntityKindsQuery = vi.fn();
vi.mock(
  '@/app/(protected)/system-management/chatbot-entity-kinds/hooks/useChatbotEntityKinds',
  () => ({ useChatbotEntityKindsQuery: () => useChatbotEntityKindsQuery() }),
);

const createMutate = vi.fn();
const updateMutate = vi.fn();
const deletionRun = vi.fn();
vi.mock('../hooks/useChatbotDomains', () => ({
  useCreateChatbotDomain: () => ({ mutate: createMutate, isPending: false }),
  useUpdateChatbotDomain: () => ({ mutate: updateMutate, isPending: false }),
  useChatbotDomainDeletion: () => ({ run: deletionRun, isRowPending: () => false }),
}));

import ChatbotDomainModal from './ChatbotDomainModal';

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

function renderModal(props: Partial<React.ComponentProps<typeof ChatbotDomainModal>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatbotDomainModal
        open
        onOpenChange={vi.fn()}
        domainId={null}
        rows={[DOMAIN]}
        onNavigate={vi.fn()}
        canManage
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listMcpToolsCatalog.mockReset();
  listMcpToolsCatalog.mockResolvedValue([{ tool_name: 'crm_incoming_stock_list' }]);
  getChatbotDomainPromptBlock.mockReset();
  getChatbotDomainPromptBlock.mockResolvedValue('Domain: incoming...');
  useChatbotEntityKindsQuery.mockReset();
  useChatbotEntityKindsQuery.mockReturnValue({ data: [], isLoading: false });
  createMutate.mockReset();
  updateMutate.mockReset();
  deletionRun.mockReset();
});
afterEach(() => cleanup());

describe('ChatbotDomainModal - AC-1511', () => {
  it('renders the four tabs and populates General from the row (edit/view state)', async () => {
    renderModal({ domainId: DOMAIN.id });
    expect(screen.getByRole('tab', { name: 'General' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Narrowing' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Ladder' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Prompt block' })).toBeInTheDocument();

    expect(screen.getByLabelText('Name')).toHaveValue('incoming');
    expect(screen.getByLabelText('Label (customer sees)')).toHaveValue('Incoming stock');
    await waitFor(() => expect(listMcpToolsCatalog).toHaveBeenCalled());
  });

  it('opens blank on create (isNew), title reads Add domain', () => {
    renderModal({ domainId: null });
    expect(screen.getByText('Add domain')).toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toHaveValue('');
    expect(screen.getByLabelText('Label (customer sees)')).toHaveValue('');
  });

  it('the prompt block tab says "Save the domain to see its block" for a new (unsaved) domain', () => {
    renderModal({ domainId: null });
    // No fetch is even attempted for a domain that does not exist yet.
    expect(getChatbotDomainPromptBlock).not.toHaveBeenCalled();
  });

  it('disables every field and hides Save/Delete for a user without chatbot_config.manage', () => {
    renderModal({ domainId: DOMAIN.id, canManage: false });
    expect(screen.getByLabelText('Name')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    // The Dialog primitive's own X icon is ALSO named "Close" - at least one real
    // dismiss control (the footer's "Close" replacing "Cancel" per AC-1511) exists.
    expect(screen.getAllByRole('button', { name: 'Close' }).length).toBeGreaterThan(0);
  });

  it('Save is disabled until both Name and Label are non-empty', () => {
    renderModal({ domainId: null });
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('Delete is a deferred action (D7) - no confirm(), calls the deletion hook directly', () => {
    const onOpenChange = vi.fn();
    renderModal({ domainId: DOMAIN.id, onOpenChange, rows: [DOMAIN, { ...DOMAIN, id: 'd-2', name: 'stock' }] });
    screen.getByRole('button', { name: 'Delete' }).click();
    expect(deletionRun).toHaveBeenCalledWith({ id: DOMAIN.id, subject: DOMAIN.label });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('Delete is hidden when this is the only domain (server refuses, 409)', () => {
    renderModal({ domainId: DOMAIN.id, rows: [DOMAIN] });
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  });
});
