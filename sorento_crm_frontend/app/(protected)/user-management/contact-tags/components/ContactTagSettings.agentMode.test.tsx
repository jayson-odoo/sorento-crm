/**
 * AGENT-MODE-TAG: agent mode is a tag chatbot setting, beside AI replies. Red first.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/user-management/contact-tags/t1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

// Catalog fetches the group editors make (access types, brands, agents ...): empty lists.
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }),
}));

const updateContactTag = vi.fn();
vi.mock('../services/contactTagService', () => ({
  updateContactTag: (...a: unknown[]) => updateContactTag(...a),
  getContactTag: vi.fn(),
  getContactTags: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0 } }),
}));

import ContactTagSettings from './ContactTagSettings';

const tag = (settings: Record<string, unknown>) => ({
  id: 't1', name: 'Dealer', description: null, is_active: true, sort_order: 0, settings,
  contact_count: 0, created_at: '', updated_at: '',
});

function render(settings: Record<string, unknown>, editing: boolean, onDone = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  rtlRender(
    <QueryClientProvider client={client}>
      <ContactTagSettings tag={tag(settings) as never} editing={editing} onDone={onDone} />
    </QueryClientProvider>,
  );
  return { onDone };
}

const group = (title: string) =>
  screen
    .getAllByTestId('settings-group')
    .find((g) => within(g).getByTestId('settings-group-title').textContent === title)!;

beforeEach(() => {
  vi.clearAllMocks();
  updateContactTag.mockResolvedValue(tag({}));
});

describe('ContactTagSettings - Agent mode (AGENT-MODE-TAG)', () => {
  it('a tag that sets agent mode shows it in the Chatbot group', () => {
    render({ chatbot: { chatbot_agent_enabled: true } }, false);
    expect(within(group('Chatbot')).getByText('Agent mode')).toBeInTheDocument();
    expect(within(group('Chatbot')).getByText('On')).toBeInTheDocument();
  });

  it('agent mode can be set on a tag and is saved under chatbot', async () => {
    render({}, true);
    fireEvent.click(within(group('Chatbot')).getByRole('switch', { name: /set on this tag/i }));
    const row = screen.getByTestId('setting-row-chatbot_agent_enabled');
    expect(within(row).getByText('Agent mode')).toBeInTheDocument();
    fireEvent.click(within(row).getByRole('radio', { name: 'On' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updateContactTag).toHaveBeenCalled());
    expect(updateContactTag.mock.calls[0][1]).toEqual({ settings: { chatbot: { chatbot_agent_enabled: true } } });
  });
});
