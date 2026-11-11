/**
 * TRACE-SIDEBAR (owner, 11 Nov 2026): "View full trace" on an expanded AI Usage row opens the
 * reply's trace in a side drawer over the usage page. It no longer navigates to the trace page.
 */
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';

const push = vi.fn();
const ok = (data: unknown) => ({ data, isLoading: false, isError: false });

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/system-management/ai-assistant/usage',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('../hooks/useAIUsage', () => ({
  useUsageSummary: () =>
    ok({ total_messages: 1, prompt_tokens: 1, completion_tokens: 1, total_tokens: 2, cost_usd: 0, unpriced_calls: 0, unknown_cache_calls: 0 }),
  useUsageByDay: () => ok([]),
  useTopUsers: () => ok([]),
  useTopContacts: () => ok([]),
  useRecentQueries: () =>
    ok([
      {
        message_id: 'msg-1',
        user_name: 'Tester',
        contact_name: null,
        contact_phone: null,
        feature: 'ai_assistant',
        form_key: null,
        query_preview: 'stock for X',
        response_time_ms: 120,
        tokens: 100,
        created_at: '2026-11-10T14:23:33',
        model: 'model-a',
        cost_usd: 0.001,
        priced: true,
        cached_price_missing: false,
        cache_unknown: false,
      },
    ]),
  useQueryDetail: () => ok({ reply: 'ok', tools_used: [] }),
}));
vi.mock('../components/TraceView', () => ({
  TraceView: ({ messageId }: { messageId: string }) => <div data-testid="trace-view-stub" data-message={messageId} />,
}));

import AIUsagePage from './page';

afterEach(() => cleanup());

describe('AI Usage View full trace opens in the side drawer (TRACE-SIDEBAR)', () => {
  it('opens the trace drawer in place, no link, no navigation', async () => {
    render(<AIUsagePage />);
    fireEvent.click(screen.getByText('stock for X'));
    const trigger = screen.getByTestId('view-trace-link');
    expect(trigger.tagName).toBe('BUTTON');
    expect(trigger.getAttribute('href')).toBeNull();
    fireEvent.click(trigger);
    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByTestId('trace-view-stub').getAttribute('data-message')).toBe('msg-1');
    expect(push).not.toHaveBeenCalled();
  });
});
