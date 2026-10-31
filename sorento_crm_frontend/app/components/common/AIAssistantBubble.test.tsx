import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

/**
 * UAC AC-N5(c): the global assistant launcher is a slim edge tab pinned to the
 * bottom-right SCREEN edge, not a round FAB floating over the page. The FAB sat
 * at z-[120] - above every Sheet (z-50) - so it covered a drawer's bottom
 * controls. What is pinned here is the geometry and the stacking, at both
 * widths, plus that opening/closing still works.
 *
 * UPDATED 2026-08-18: the tab collapses to the side. Collapsed is a 32px-wide
 * VERTICAL handle (the horizontal pill was ~130px wide and sat on table rows),
 * the panel carries an explicit collapse control, and the choice is persisted so
 * it survives navigation and reload - collapsed for a first-time user.
 */
const hasPermission = vi.fn((_slug?: string) => true);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug?: string) => hasPermission(slug),
}));

let currentSearchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => currentSearchParams,
}));

vi.mock('@/lib/aiAssistantChatApi', () => ({
  fetchAIAssistantGreeting: vi.fn(async () => ({ greeting: 'Hi' })),
  listAIAssistantConversations: vi.fn(async () => []),
  loadConversation: vi.fn(async () => ({ messages: [] })),
  sendAIAssistantMessage: vi.fn(async () => ({ messages: [] })),
  confirmPanelAction: vi.fn(),
  cancelPanelAction: vi.fn(),
  withdrawPanelStep: vi.fn(),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/aiPageSnapshot', () => ({
  getPageSnapshot: () => null,
}));

import * as chatApi from '@/lib/aiAssistantChatApi';
import { toast } from '@/lib/toast';
import AIAssistantBubble from './AIAssistantBubble';

const OPEN_STORAGE_KEY = 'sorento.ai.bubbleOpen';

function handle() {
  return screen.getByTestId('ai-assistant-tab');
}

function collapseButton() {
  return screen.getByTestId('ai-assistant-collapse');
}

describe('AIAssistantBubble edge-tab launcher (AC-N5c)', () => {
  beforeEach(() => {
    hasPermission.mockReturnValue(true);
    window.localStorage.clear();
  });

  it('renders nothing without the assistant permission', () => {
    hasPermission.mockReturnValue(false);
    const { container } = render(<AIAssistantBubble />);
    expect(container.firstChild).toBeNull();
  });

  it('anchors to the bottom-right screen edge under any open sheet', () => {
    render(<AIAssistantBubble />);
    const root = document.querySelector('[data-ai-assistant-root]');
    const rootClass = root?.getAttribute('class') ?? '';
    expect(rootClass).toContain('fixed');
    expect(rootClass).toContain('end-0');
    expect(rootClass).toContain('bottom-6');
    // Above header (z-10) / sidebar (z-20), below Sheet + Dialog (z-50).
    expect(rootClass).toContain('z-40');
    expect(rootClass).not.toContain('z-[120]');
  });

  it('is a slim 32px vertical handle hugging the edge, not a wide pill or a FAB', () => {
    render(<AIAssistantBubble />);
    const cls = handle().getAttribute('class') ?? '';
    expect(cls).toContain('w-8');
    expect(cls).toContain('flex-col');
    expect(cls).toContain('rounded-s-lg');
    expect(cls).not.toContain('rounded-full');
  });

  it('rotates the label into the handle from sm up and shows the icon alone at phone width', () => {
    render(<AIAssistantBubble />);
    const label = screen.getByText('AI assistant');
    const cls = label.getAttribute('class') ?? '';
    // 375px: `hidden`. 1280px: `sm:inline`, running down the handle.
    expect(cls).toContain('hidden');
    expect(cls).toContain('sm:inline');
    expect(cls).toContain('[writing-mode:vertical-rl]');
  });
});

describe('AIAssistantBubble collapse to the side', () => {
  beforeEach(() => {
    hasPermission.mockReturnValue(true);
    window.localStorage.clear();
  });

  it('is collapsed for a first-time user: handle only, no panel', () => {
    render(<AIAssistantBubble />);
    expect(handle().getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByTestId('ai-assistant-panel')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'AI assistant' })).toBeNull();
  });

  it('expands on click, replacing the handle with the panel', async () => {
    render(<AIAssistantBubble />);
    fireEvent.click(handle());

    expect(screen.getByTestId('ai-assistant-panel')).toBeDefined();
    expect(screen.getByRole('heading', { name: 'AI assistant' })).toBeDefined();
    // The handle now fades out over --duration-fast (M3-07) rather than
    // unmounting on the same tick, so it stays mounted for its own exit -
    // it still unmounts once that exit completes, and the two never overlap.
    await waitFor(() => expect(screen.queryByTestId('ai-assistant-tab')).toBeNull());
    expect(collapseButton().getAttribute('aria-expanded')).toBe('true');
  });

  it('collapses again from the panel control, returning the handle', async () => {
    render(<AIAssistantBubble />);
    fireEvent.click(handle());
    fireEvent.click(collapseButton());

    // The panel now materialises/dematerialises on the shared spring (S8-05),
    // so it stays mounted for its exit animation rather than vanishing on the
    // same tick the control is clicked.
    await waitFor(() => expect(screen.queryByTestId('ai-assistant-panel')).toBeNull());
    expect(handle().getAttribute('aria-expanded')).toBe('false');
  });

  it('persists expanding and collapsing to localStorage', () => {
    render(<AIAssistantBubble />);
    expect(window.localStorage.getItem(OPEN_STORAGE_KEY)).toBeNull();

    fireEvent.click(handle());
    expect(window.localStorage.getItem(OPEN_STORAGE_KEY)).toBe('1');

    fireEvent.click(collapseButton());
    expect(window.localStorage.getItem(OPEN_STORAGE_KEY)).toBe('0');
  });

  it('restores the expanded panel from localStorage', async () => {
    window.localStorage.setItem(OPEN_STORAGE_KEY, '1');
    render(<AIAssistantBubble />);

    // `open` starts false and flips true from an effect reading localStorage,
    // so the handle briefly mounts before exiting (M3-07's fade) - same
    // "expands" path as a click, just effect-driven instead of user-driven.
    expect(screen.getByTestId('ai-assistant-panel')).toBeDefined();
    await waitFor(() => expect(screen.queryByTestId('ai-assistant-tab')).toBeNull());
  });

  it('stays collapsed when localStorage says collapsed', () => {
    window.localStorage.setItem(OPEN_STORAGE_KEY, '0');
    render(<AIAssistantBubble />);

    expect(screen.queryByTestId('ai-assistant-panel')).toBeNull();
    expect(handle().getAttribute('aria-expanded')).toBe('false');
  });

  it('moves focus with the toggle so a keyboard user is never dropped on the body', () => {
    render(<AIAssistantBubble />);
    fireEvent.click(handle());
    expect(document.activeElement).toBe(screen.getByTestId('ai-assistant-panel'));

    fireEvent.click(collapseButton());
    expect(document.activeElement).toBe(handle());
  });
});

describe('AIAssistantBubble resize (M3-07)', () => {
  beforeEach(() => {
    hasPermission.mockReturnValue(true);
    window.localStorage.clear();
  });

  it('does not re-render on pointermove, only once on pointerup', () => {
    const onRender = vi.fn();
    render(
      <React.Profiler id="ai-bubble" onRender={onRender}>
        <AIAssistantBubble />
      </React.Profiler>,
    );
    fireEvent.click(handle());
    const corner = screen.getByTestId('ai-assistant-resize-corner');
    onRender.mockClear();

    fireEvent.pointerDown(corner, { clientX: 100, clientY: 100, pointerId: 1 });
    // pointerdown only arms local listeners - no state write, so no render.
    expect(onRender).not.toHaveBeenCalled();

    fireEvent.pointerMove(corner, { clientX: 90, clientY: 90, pointerId: 1 });
    fireEvent.pointerMove(corner, { clientX: 70, clientY: 60, pointerId: 1 });
    fireEvent.pointerMove(corner, { clientX: 40, clientY: 30, pointerId: 1 });
    // Every move so far wrote straight to the panel's own DOM style, rAF-
    // throttled - none of it went through React state.
    expect(onRender).not.toHaveBeenCalled();

    fireEvent.pointerUp(corner, { clientX: 40, clientY: 30, pointerId: 1 });
    // The one point a re-render is needed - to persist the final size.
    expect(onRender).toHaveBeenCalledTimes(1);
  });

  it('writes the dragged size to the panel element during the move', async () => {
    render(<AIAssistantBubble />);
    fireEvent.click(handle());
    const panel = screen.getByTestId('ai-assistant-panel');
    const corner = screen.getByTestId('ai-assistant-resize-corner');
    const startWidth = panel.style.width;

    fireEvent.pointerDown(corner, { clientX: 100, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(corner, { clientX: 40, clientY: 40, pointerId: 1 });
    // The write is rAF-throttled - real timers here, so wait one real frame.
    await act(async () => {
      await new Promise((resolve) => requestAnimationFrame(resolve));
    });

    // Dragging the corner up-left grows both dimensions - written directly
    // onto the panel's style, independent of whether React has re-rendered.
    expect(panel.style.width).not.toBe(startWidth);

    fireEvent.pointerUp(corner, { clientX: 40, clientY: 40, pointerId: 1 });
  });

  it('presses rather than widening on hover, and stays a real button', () => {
    render(<AIAssistantBubble />);
    // `transition-all hover:w-9` grew the handle on hover and, because `all`
    // includes opacity, smeared the AnimatePresence exit it now has (M3-07).
    // The press is the shared class every other control uses.
    expect(handle().className).not.toContain('transition-all');
    expect(handle().className).not.toContain('hover:w-9');
    expect(handle().className).toContain('active:scale-[0.97]');
    // The exit behaviour itself (fading rather than vanishing) is covered by
    // the "expands on click" test above, which has to `waitFor` the unmount.
    expect(handle().tagName).toBe('BUTTON');
  });
});

// ---------------------------------------------------------------------------
// AGENTIC-UNIFY PR 3, slice 4 (red): the panel draws the brain's replies (AC-21 to AC-23, AC-26).
//
// A reply is a "brain reply" when `metadata_json.route` is set; one without it is today's markdown
// reply. The server decides what the reader may see and what state a card is in; the panel only
// draws what it reads back, so Confirm, Cancel and Undo each call the server and then read the
// thread again (`loadConversation`) and draw THAT, with no local outcome state.
// Threads are opened through the deep link (?ai_conversation=conv-1), the way a real reader gets one.
// ---------------------------------------------------------------------------

const USE_SLUG = 'system.ai_assistant_chat.use';
const VIEW_SLUG = 'system.ai_assistant_settings.view';
const TURN = '5b0c1f2e-3a4d-4e6f-8a9b-0c1d2e3f4a5b';
const ACTION = '7c1d2e3f-4a5b-4c6d-9e0f-1a2b3c4d5e6f';

const inAMinute = () => new Date(Date.now() + 60_000).toISOString().replace('Z', '');

function user(id = 'u1') {
  return { id, role: 'user', content: 'ZZT question', metadata_json: {}, created_at: '2026-10-30T09:00:00Z' };
}

function brain(over: Record<string, unknown> = {}, meta: Record<string, unknown> = {}, id = 'm-brain') {
  return {
    id,
    role: 'assistant',
    content: 'ZZT reply',
    created_at: '2026-10-30T09:00:05Z',
    metadata_json: { route: 'agent', status: 'done', chatbot_turn_id: TURN, ...meta },
    ...over,
  };
}

const PENDING = { id: ACTION, turn_id: TURN, lines: ['Approve PR-1 for Example Trading.'], expires_at: '2099-01-01T00:00:00Z' };
const FULL_AGENT = {
  turn_id: TURN,
  reply_text: 'ZZT reply',
  status: 'answered',
  limit_hit: null,
  rounds: 2,
  usage: { prompt_tokens: 10, completion_tokens: 5, cached_tokens: 0, calls: 2 },
  tool_calls: [{ name: 'crm_inventory_stock_balance_list', status: 'ok', ms: 12 }],
  steps: {
    rounds: 2,
    prompt_tokens: 10,
    completion_tokens: 5,
    cached_tokens: 0,
    tool_calls: [{ name: 'crm_inventory_stock_balance_list', status: 'ok', ms: 12 }],
  },
  pending_action: null,
  actions: [],
};
const ROUTE_DECISION = { side: 'agent', reason: 'classified', score: 0.93, model: 'jev-1.14.0', ms: 100, error: null };

function grant(...slugs: string[]) {
  const held = new Set([USE_SLUG, ...slugs]);
  hasPermission.mockImplementation((slug?: string) => held.has(String(slug)));
}

async function openThread(messages: unknown[]) {
  vi.mocked(chatApi.loadConversation).mockResolvedValueOnce({ id: 'conv-1', title: null, created_at: '', updated_at: '', messages } as never);
  currentSearchParams = new URLSearchParams('ai_conversation=conv-1');
  const view = render(<AIAssistantBubble />);
  await waitFor(() => expect(screen.getByTestId('ai-assistant-panel')).toBeDefined());
  await waitFor(() => expect(screen.getByText('ZZT question')).toBeDefined());
  return view;
}

function nextThread(messages: unknown[]) {
  vi.mocked(chatApi.loadConversation).mockResolvedValueOnce({ id: 'conv-1', title: null, created_at: '', updated_at: '', messages } as never);
}

beforeEach(() => {
  window.localStorage.clear();
  currentSearchParams = new URLSearchParams();
  vi.mocked(chatApi.loadConversation).mockReset();
  vi.mocked(chatApi.loadConversation).mockResolvedValue({ messages: [] } as never);
  vi.mocked(chatApi.confirmPanelAction).mockReset();
  vi.mocked(chatApi.cancelPanelAction).mockReset();
  vi.mocked(chatApi.withdrawPanelStep).mockReset();
  vi.mocked(chatApi.sendAIAssistantMessage).mockClear();
  vi.mocked(toast.error).mockClear();
});

describe('AIAssistantBubble: which renderer a reply gets (AC-21, AC-26)', () => {
  it('draws a brain reply as a real list with no raw marker', async () => {
    grant();
    await openThread([user(), brain({ content: 'Stock:\n- *Alpha* is low\n- Beta is fine' })]);

    const items = screen.getAllByRole('listitem');
    expect(items.map((li) => li.textContent)).toEqual(['Alpha is low', 'Beta is fine']);
    expect(items[0].querySelector('strong')?.textContent).toBe('Alpha');
    expect(screen.getByTestId('ai-assistant-panel').textContent).not.toContain('*');
  });

  it('keeps an old reply (no route) on markdown, including a table', async () => {
    grant();
    await openThread([
      user(),
      {
        id: 'm-old',
        role: 'assistant',
        content: '| Item | Qty |\n| --- | --- |\n| Alpha | 5 |',
        created_at: '2026-10-30T09:00:05Z',
        metadata_json: {},
      },
    ]);

    expect(document.querySelector('table')).not.toBeNull();
    expect(screen.getByRole('columnheader', { name: 'Item' })).toBeDefined();
    expect(screen.getByRole('cell', { name: 'Alpha' })).toBeDefined();
  });

  it('draws the files of a brain reply with TurnAttachments', async () => {
    grant();
    await openThread([
      user(),
      brain({}, {
        attachments: [
          { url: 'https://files.example.invalid/spec.pdf', filename: 'spec.pdf', mimeType: 'application/pdf', attachmentType: 'specification' },
        ],
      }),
    ]);

    const files = screen.getByTestId('turn-attachments');
    expect(files.textContent).toContain('spec.pdf');
    expect(files.textContent).toContain('application/pdf');
  });

  it('shows no attachment block on a brain reply with no files', async () => {
    grant();
    await openThread([user(), brain({}, { attachments: [] })]);
    expect(screen.queryByTestId('turn-attachments')).toBeNull();
  });
});

describe('AIAssistantBubble: cards for everyone, the trace for the settings slug (AC-22, AC-23)', () => {
  const proposing = () => brain({}, { agent: { ...FULL_AGENT, pending_action: PENDING } });

  it('shows Confirm and Cancel on a reply holding a pending action, without the settings slug', async () => {
    grant();
    await openThread([user(), proposing()]);

    const card = screen.getByTestId('agent-proposal');
    expect(card.textContent).toContain('Confirm change');
    expect(card.textContent).toContain('Cancel');
  });

  it('shows the actions block of a reply, without the settings slug', async () => {
    grant();
    await openThread([
      user(),
      brain({}, {
        agent: {
          pending_action: null,
          actions: [{ id: ACTION, status: 'executed', decided_at: null, decided_by_name: 'Pat', steps: [{ summary: 'Approve PR-1', status: 'done', error: null, changes: [], waiting: null }] }],
        },
      }),
    ]);

    const block = screen.getByTestId('agent-actions');
    expect(block.textContent).toContain('Approve PR-1');
    expect(block.textContent).toContain('Done');
    expect(screen.queryByTestId('agent-proposal')).toBeNull();
  });

  it('shows the route pill, steps and reply meta with the settings slug', async () => {
    grant(VIEW_SLUG);
    await openThread([user(), brain({}, { route_decision: ROUTE_DECISION, agent: FULL_AGENT })]);

    expect(screen.getByRole('button', { name: 'Agent' })).toBeDefined();
    expect(screen.getByTestId('agent-steps')).toBeDefined();
    expect(screen.getByTestId('agent-reply-meta')).toBeDefined();
  });

  it('hides the pill, steps and reply meta without the settings slug, even when the data is present', async () => {
    grant();
    await openThread([user(), brain({}, { route_decision: ROUTE_DECISION, agent: FULL_AGENT })]);

    expect(screen.queryByRole('button', { name: 'Agent' })).toBeNull();
    expect(screen.queryByTestId('agent-steps')).toBeNull();
    expect(screen.queryByTestId('agent-reply-meta')).toBeNull();
    expect(screen.queryByTestId('bubble-view-trace')).toBeNull();
  });

  it('links a brain reply to the chat history turn, with the settings slug', async () => {
    grant(VIEW_SLUG);
    await openThread([user(), brain({}, { route_decision: ROUTE_DECISION, agent: FULL_AGENT })]);

    expect(screen.getByTestId('bubble-view-trace').getAttribute('href')).toBe(
      `/system-management/chat-history?turn=${TURN}`,
    );
  });

  it('keeps the usage trace link on an old reply', async () => {
    grant(VIEW_SLUG);
    await openThread([
      user(),
      { id: 'm-old', role: 'assistant', content: 'ZZT old', created_at: '2026-10-30T09:00:05Z', metadata_json: {} },
    ]);

    expect(screen.getByTestId('bubble-view-trace').getAttribute('href')).toBe(
      '/system-management/ai-assistant/usage/trace/m-old',
    );
  });
});

describe('AIAssistantBubble: a decision is read back from the server (AC-22)', () => {
  const proposing = () => brain({}, { agent: { ...FULL_AGENT, pending_action: PENDING } });
  const decided = (status: string, summary = 'Approve PR-1') => [
    user(),
    brain({}, {
      agent: {
        pending_action: null,
        actions: [{ id: ACTION, status, decided_at: null, decided_by_name: 'Pat', steps: [{ summary, status: status === 'executed' ? 'done' : 'skipped', error: null, changes: [], waiting: null }] }],
      },
    }),
    brain({ id: 'm-outcome', content: status === 'executed' ? 'Done. I made these changes:' : 'Cancelled. Nothing was changed.', created_at: '2026-10-30T09:01:00Z' }, { status }),
  ];

  it('Confirm calls the server, reloads the thread and draws what came back', async () => {
    grant();
    await openThread([user(), proposing()]);
    vi.mocked(chatApi.confirmPanelAction).mockResolvedValueOnce({ action_id: ACTION, status: 'executed', reply_text: 'Done.', steps: [] });
    nextThread(decided('executed'));
    const loads = vi.mocked(chatApi.loadConversation).mock.calls.length;

    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));

    await waitFor(() => expect(screen.queryByTestId('agent-proposal')).toBeNull());
    expect(chatApi.confirmPanelAction).toHaveBeenCalledWith(ACTION);
    expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(loads + 1);
    expect(vi.mocked(chatApi.loadConversation).mock.calls.at(-1)?.[0]).toBe('conv-1');
    expect(screen.getByTestId('agent-actions').textContent).toContain('Done');
    expect(screen.getByText('Done. I made these changes:')).toBeDefined();
  });

  it('Cancel calls the server, reloads the thread and draws what came back', async () => {
    grant();
    await openThread([user(), proposing()]);
    vi.mocked(chatApi.cancelPanelAction).mockResolvedValueOnce({ action_id: ACTION, status: 'cancelled', reply_text: 'Cancelled.', steps: [] });
    nextThread(decided('cancelled'));
    const loads = vi.mocked(chatApi.loadConversation).mock.calls.length;

    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByTestId('agent-proposal')).toBeNull());
    expect(chatApi.cancelPanelAction).toHaveBeenCalledWith(ACTION);
    expect(chatApi.confirmPanelAction).not.toHaveBeenCalled();
    expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(loads + 1);
    expect(screen.getByText('Cancelled. Nothing was changed.')).toBeDefined();
  });

  it('keeps no local outcome: if the reloaded thread still says waiting, the card is still there', async () => {
    grant();
    await openThread([user(), proposing()]);
    vi.mocked(chatApi.confirmPanelAction).mockResolvedValueOnce({ action_id: ACTION, status: 'executed', reply_text: 'Done.', steps: [] });
    nextThread([user(), proposing()]);
    const loads = vi.mocked(chatApi.loadConversation).mock.calls.length;

    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));

    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(loads + 1));
    await waitFor(() => expect(screen.getByTestId('agent-proposal')).toBeDefined());
    expect(screen.queryByTestId('agent-action-outcome')).toBeNull();
  });

  it('Undo withdraws the step by action id and index, then reloads the thread', async () => {
    grant();
    const waitingThread = () => [
      user(),
      brain({}, {
        agent: {
          pending_action: null,
          actions: [{
            id: ACTION, status: 'executed', decided_at: null, decided_by_name: 'Pat',
            steps: [
              { summary: 'Approve PR-1', status: 'done', error: null, changes: [], waiting: null },
              { summary: 'Rename customer', status: 'done', error: null, changes: [], waiting: { commit_at: inAMinute(), window_seconds: 60 } },
            ],
          }],
        },
      }),
    ];
    await openThread(waitingThread());
    vi.mocked(chatApi.withdrawPanelStep).mockResolvedValueOnce({ action_id: ACTION, status: 'executed', reply_text: 'Withdrawn.', steps: [] });
    nextThread([user(), brain({}, { agent: { pending_action: null, actions: [{ id: ACTION, status: 'executed', decided_at: null, decided_by_name: 'Pat', steps: [
      { summary: 'Approve PR-1', status: 'done', error: null, changes: [], waiting: null },
      { summary: 'Rename customer', status: 'withdrawn', error: null, changes: [], waiting: null },
    ] }] } })]);
    const loads = vi.mocked(chatApi.loadConversation).mock.calls.length;

    fireEvent.click(within(screen.getByTestId('agent-step-waiting')).getByRole('button', { name: 'Undo' }));

    await waitFor(() => expect(screen.queryByTestId('agent-step-waiting')).toBeNull());
    expect(chatApi.withdrawPanelStep).toHaveBeenCalledWith(ACTION, 1);
    expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(loads + 1);
  });

  it('a refused decision shows its plain reason as a toast and reloads the thread', async () => {
    grant();
    await openThread([user(), proposing()]);
    vi.mocked(chatApi.confirmPanelAction).mockRejectedValueOnce(new Error('This proposal was already decided.'));
    nextThread(decided('executed'));
    const loads = vi.mocked(chatApi.loadConversation).mock.calls.length;

    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(vi.mocked(toast.error).mock.calls[0][0]).toBe('This proposal was already decided.');
    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(loads + 1));
    await waitFor(() => expect(screen.queryByTestId('agent-proposal')).toBeNull());
    expect(screen.getByTestId('ai-assistant-panel')).toBeDefined();
  });
});

describe('AIAssistantBubble: the old write-confirm card is unchanged (AC-26)', () => {
  it('still shows Confirm and Cancel for pending_confirmation and sends the decision as a turn', async () => {
    grant();
    await openThread([
      user(),
      {
        id: 'm-old',
        role: 'assistant',
        content: 'ZZT change the phone number?',
        created_at: '2026-10-30T09:00:05Z',
        metadata_json: { pending_confirmation: { tool_name: 'zzt_tool', status: 'pending', summary: 'x' } },
      },
    ]);

    expect(screen.getByTestId('write-confirm-actions')).toBeDefined();
    expect(screen.queryByTestId('agent-proposal')).toBeNull();
    fireEvent.click(screen.getByTestId('write-confirm-btn'));

    await waitFor(() => expect(chatApi.sendAIAssistantMessage).toHaveBeenCalled());
    const call = vi.mocked(chatApi.sendAIAssistantMessage).mock.calls[0];
    expect(call[0]).toBe('Confirm');
    expect(call[3]).toBe('confirm');
    expect(chatApi.confirmPanelAction).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// AGENTIC-UNIFY PR 3, review round 1 (red): races between a decision's reload and the reader moving on,
// a double click, a countdown's end, and a trace link with nothing to point at.
// ---------------------------------------------------------------------------

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const OUTCOME = { action_id: ACTION, status: 'executed', reply_text: 'Done.', steps: [] };

function proposingThread() {
  return [
    user(),
    brain({}, { agent: { ...FULL_AGENT, pending_action: PENDING } }, 'm-prop'),
  ];
}

function otherThread() {
  return [
    { id: 'u2', role: 'user', content: 'ZZT other question', metadata_json: {}, created_at: '2026-10-30T10:00:00Z' },
    { id: 'm-other', role: 'assistant', content: 'ZZT other answer', metadata_json: {}, created_at: '2026-10-30T10:00:05Z' },
  ];
}

async function pickOtherThread() {
  vi.mocked(chatApi.listAIAssistantConversations).mockResolvedValueOnce({
    items: [{ id: 'conv-2', title: 'ZZT other thread', updated_at: '2026-10-30T10:00:05Z' }],
  } as never);
  fireEvent.click(screen.getByLabelText('Show conversation history'));
  const row = await screen.findByText('ZZT other thread');
  vi.mocked(chatApi.loadConversation).mockResolvedValueOnce({ id: 'conv-2', title: null, created_at: '', updated_at: '', messages: otherThread() } as never);
  fireEvent.click(row);
  await waitFor(() => expect(screen.getByText('ZZT other answer')).toBeDefined());
}

describe('AIAssistantBubble: a reload for a thread no longer open is thrown away (review round 1)', () => {
  it('drops the first thread\'s reload after another thread was picked, and keeps the new thread\'s id', async () => {
    grant();
    await openThread(proposingThread());
    const confirm = deferred<typeof OUTCOME>();
    vi.mocked(chatApi.confirmPanelAction).mockReturnValueOnce(confirm.promise as never);
    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));
    await waitFor(() => expect(chatApi.confirmPanelAction).toHaveBeenCalled());

    await pickOtherThread();
    // the decision lands now; its reload is for conv-1, which is no longer the thread on screen
    const reload = deferred<unknown>();
    vi.mocked(chatApi.loadConversation).mockReturnValueOnce(reload.promise as never);
    confirm.resolve(OUTCOME);
    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.at(-1)?.[0]).toBe('conv-1'));
    reload.resolve({ id: 'conv-1', title: null, created_at: '', updated_at: '', messages: proposingThread() });

    await act(async () => { await Promise.resolve(); });
    await waitFor(() => expect(screen.queryByTestId('agent-proposal')).toBeNull());
    expect(screen.getByText('ZZT other answer')).toBeDefined();
    expect(screen.queryByText('ZZT question')).toBeNull();

    // the thread on screen is still conv-2: a send goes to it
    vi.mocked(chatApi.sendAIAssistantMessage).mockResolvedValueOnce({ id: 'conv-2', messages: otherThread() } as never);
    fireEvent.change(screen.getByPlaceholderText('Ask the assistant...'), { target: { value: 'ZZT next' } });
    fireEvent.click(screen.getByLabelText('Send message'));
    await waitFor(() => expect(chatApi.sendAIAssistantMessage).toHaveBeenCalled());
    expect(vi.mocked(chatApi.sendAIAssistantMessage).mock.calls[0][1]).toBe('conv-2');
  });

  it('control: with the same thread still open, the reload is drawn', async () => {
    grant();
    await openThread(proposingThread());
    const confirm = deferred<typeof OUTCOME>();
    vi.mocked(chatApi.confirmPanelAction).mockReturnValueOnce(confirm.promise as never);
    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));
    await waitFor(() => expect(chatApi.confirmPanelAction).toHaveBeenCalled());
    nextThread([user(), brain({}, { agent: { pending_action: null, actions: [] } }, 'm-prop')]);

    confirm.resolve(OUTCOME);

    await waitFor(() => expect(screen.queryByTestId('agent-proposal')).toBeNull());
  });

  it('drops the reload after New chat, and the new chat stays empty', async () => {
    grant();
    await openThread(proposingThread());
    const confirm = deferred<typeof OUTCOME>();
    vi.mocked(chatApi.confirmPanelAction).mockReturnValueOnce(confirm.promise as never);
    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));
    await waitFor(() => expect(chatApi.confirmPanelAction).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText('Start new conversation'));
    await waitFor(() => expect(screen.queryByText('ZZT question')).toBeNull());
    const reload = deferred<unknown>();
    vi.mocked(chatApi.loadConversation).mockReturnValueOnce(reload.promise as never);
    confirm.resolve(OUTCOME);
    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBeGreaterThan(1));
    reload.resolve({ id: 'conv-1', title: null, created_at: '', updated_at: '', messages: proposingThread() });

    await act(async () => { await Promise.resolve(); });
    expect(screen.queryByText('ZZT question')).toBeNull();
    expect(screen.queryByTestId('agent-proposal')).toBeNull();
  });

  it('an older reload does not wipe the reply a send drew', async () => {
    grant();
    await openThread(proposingThread());
    const confirm = deferred<typeof OUTCOME>();
    vi.mocked(chatApi.confirmPanelAction).mockReturnValueOnce(confirm.promise as never);
    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));
    await waitFor(() => expect(chatApi.confirmPanelAction).toHaveBeenCalled());
    const reload = deferred<unknown>();
    vi.mocked(chatApi.loadConversation).mockReturnValueOnce(reload.promise as never);
    confirm.resolve(OUTCOME);
    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBeGreaterThan(1));

    // while the reload is out, the user sends and the send's answer is drawn
    const sent = [...proposingThread(), { id: 'u3', role: 'user', content: 'ZZT follow up', metadata_json: {}, created_at: '2026-10-30T09:05:00Z' }, { id: 'm-new', role: 'assistant', content: 'ZZT NEWEST REPLY', metadata_json: {}, created_at: '2026-10-30T09:05:05Z' }];
    vi.mocked(chatApi.sendAIAssistantMessage).mockResolvedValueOnce({ id: 'conv-1', messages: sent } as never);
    fireEvent.change(screen.getByPlaceholderText('Ask the assistant...'), { target: { value: 'ZZT follow up' } });
    fireEvent.click(screen.getByLabelText('Send message'));
    await waitFor(() => expect(chatApi.sendAIAssistantMessage).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText('ZZT NEWEST REPLY')).toBeDefined());
    reload.resolve({ id: 'conv-1', title: null, created_at: '', updated_at: '', messages: proposingThread() });

    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText('ZZT NEWEST REPLY')).toBeDefined();
  });
});

describe('AIAssistantBubble: a decision runs once (review round 1)', () => {
  it('a double click on Confirm in one tick calls the server once', async () => {
    grant();
    await openThread(proposingThread());
    const confirm = deferred<typeof OUTCOME>();
    vi.mocked(chatApi.confirmPanelAction).mockReturnValue(confirm.promise as never);
    const button = within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ });

    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });

    expect(chatApi.confirmPanelAction).toHaveBeenCalledTimes(1);
    confirm.resolve(OUTCOME);
    await act(async () => { await Promise.resolve(); });
  });

  it('disables Confirm and Cancel while the decision is in flight', async () => {
    grant();
    await openThread(proposingThread());
    const confirm = deferred<typeof OUTCOME>();
    vi.mocked(chatApi.confirmPanelAction).mockReturnValueOnce(confirm.promise as never);
    const card = screen.getByTestId('agent-proposal');
    // control: enabled before the click
    expect((within(card).getByRole('button', { name: 'Cancel' }) as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(within(card).getByRole('button', { name: /Confirm/ }));

    await waitFor(() => expect((within(screen.getByTestId('agent-proposal')).getByRole('button', { name: 'Cancel' }) as HTMLButtonElement).disabled).toBe(true));
    expect((within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }) as HTMLButtonElement).disabled).toBe(true);
    confirm.resolve(OUTCOME);
    await act(async () => { await Promise.resolve(); });
  });
});

describe('AIAssistantBubble: a countdown\'s end reads the thread again (review round 1)', () => {
  it('reloads the thread when a waiting step\'s window closes', async () => {
    grant();
    const past = new Date(Date.now() - 5_000).toISOString().replace('Z', '');
    await openThread([
      user(),
      brain({}, { agent: { pending_action: null, actions: [{ id: ACTION, status: 'executed', decided_at: null, decided_by_name: 'Pat', steps: [{ summary: 'Rename customer', status: 'done', error: null, changes: [], waiting: { commit_at: past, window_seconds: 60 } }] }] } }),
    ]);

    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(2));
    expect(vi.mocked(chatApi.loadConversation).mock.calls[1][0]).toBe('conv-1');
  });
});

describe('AIAssistantBubble: the trace link needs a turn to point at (review round 1)', () => {
  it('has no trace link on a brain reply with no chatbot_turn_id, with the settings slug', async () => {
    grant(VIEW_SLUG);
    await openThread([
      user(),
      { id: 'm-noturn', role: 'assistant', content: 'ZZT reply', created_at: '2026-10-30T09:00:05Z', metadata_json: { route: 'agent', status: 'done', route_decision: ROUTE_DECISION } },
    ]);

    expect(screen.queryByTestId('bubble-view-trace')).toBeNull();
  });

  it('control: the same reply with a turn id has the link', async () => {
    grant(VIEW_SLUG);
    await openThread([user(), brain({}, { route_decision: ROUTE_DECISION })]);
    expect(screen.getByTestId('bubble-view-trace').getAttribute('href')).toBe(`/system-management/chat-history?turn=${TURN}`);
  });
});

// ---------------------------------------------------------------------------
// AGENTIC-UNIFY PR 3, review round 2 (red): Undo during a send, a failed send, a send for a thread no
// longer open, and the decision latch.
// ---------------------------------------------------------------------------

function waitingThread(commitAt: string) {
  return [
    user(),
    brain({}, {
      agent: {
        pending_action: null,
        actions: [{
          id: ACTION, status: 'executed', decided_at: null, decided_by_name: 'Pat',
          steps: [{ summary: 'Rename customer', status: 'done', error: null, changes: [], waiting: { commit_at: commitAt, window_seconds: 60 } }],
        }],
      },
    }),
  ];
}

function typeAndSend(text: string) {
  fireEvent.change(screen.getByPlaceholderText('Ask the assistant...'), { target: { value: text } });
  fireEvent.click(screen.getByLabelText('Send message'));
}

describe('AIAssistantBubble: Undo and a send (review round 2)', () => {
  it('keeps Undo enabled and working while a message is in flight', async () => {
    grant();
    await openThread(waitingThread(inAMinute()));
    const sending = deferred<unknown>();
    vi.mocked(chatApi.sendAIAssistantMessage).mockReturnValueOnce(sending.promise as never);
    typeAndSend('ZZT hold on');
    await waitFor(() => expect(chatApi.sendAIAssistantMessage).toHaveBeenCalled());
    const undo = within(screen.getByTestId('agent-step-waiting')).getByRole('button', { name: 'Undo' }) as HTMLButtonElement;
    expect(undo.disabled).toBe(false);
    vi.mocked(chatApi.withdrawPanelStep).mockResolvedValueOnce({ action_id: ACTION, status: 'executed', reply_text: 'Withdrawn.', steps: [] });
    nextThread(waitingThread(inAMinute()));

    fireEvent.click(undo);

    await waitFor(() => expect(chatApi.withdrawPanelStep).toHaveBeenCalledWith(ACTION, 0));
    sending.resolve({ id: 'conv-1', messages: waitingThread(inAMinute()) });
    await act(async () => { await Promise.resolve(); });
  });

  it('keeps the error bubble of a failed send when a countdown\'s reload returns after it', async () => {
    grant();
    const soon = new Date(Date.now() + 1_500).toISOString().replace('Z', '');
    await openThread(waitingThread(soon));
    const sending = deferred<unknown>();
    vi.mocked(chatApi.sendAIAssistantMessage).mockReturnValueOnce(sending.promise as never);
    typeAndSend('ZZT will fail');
    await waitFor(() => expect(chatApi.sendAIAssistantMessage).toHaveBeenCalled());
    const reload = deferred<unknown>();
    vi.mocked(chatApi.loadConversation).mockReturnValueOnce(reload.promise as never);
    // the window closes while the send is out: the countdown asks for the thread
    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(2), { timeout: 4000 });

    sending.reject(new Error('ZZT the assistant is unavailable'));
    await waitFor(() => expect(screen.getByText('ZZT the assistant is unavailable')).toBeDefined());
    reload.resolve({ id: 'conv-1', title: null, created_at: '', updated_at: '', messages: waitingThread(soon) });

    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText('ZZT the assistant is unavailable')).toBeDefined();
  }, 10_000);
});

describe('AIAssistantBubble: a send for a thread no longer open (review round 2)', () => {
  it('drops the answer to a send on thread A once thread B was picked, and keeps B\'s id', async () => {
    grant();
    await openThread(proposingThread());
    const sending = deferred<unknown>();
    vi.mocked(chatApi.sendAIAssistantMessage).mockReturnValueOnce(sending.promise as never);
    typeAndSend('ZZT on thread A');
    await waitFor(() => expect(chatApi.sendAIAssistantMessage).toHaveBeenCalled());

    await pickOtherThread();
    sending.resolve({ id: 'conv-1', messages: [...proposingThread(), { id: 'm-late', role: 'assistant', content: 'ZZT LATE ANSWER FOR A', metadata_json: {}, created_at: '2026-10-30T09:09:00Z' }] });
    await act(async () => { await Promise.resolve(); });

    expect(screen.queryByText('ZZT LATE ANSWER FOR A')).toBeNull();
    expect(screen.getByText('ZZT other answer')).toBeDefined();
    vi.mocked(chatApi.sendAIAssistantMessage).mockResolvedValueOnce({ id: 'conv-2', messages: otherThread() } as never);
    typeAndSend('ZZT on thread B');
    await waitFor(() => expect(vi.mocked(chatApi.sendAIAssistantMessage).mock.calls.length).toBe(2));
    expect(vi.mocked(chatApi.sendAIAssistantMessage).mock.calls[1][1]).toBe('conv-2');
  });

  it('control: the first send on New chat still draws its reply and sets the new id', async () => {
    grant();
    await openThread(proposingThread());
    fireEvent.click(screen.getByLabelText('Start new conversation'));
    await waitFor(() => expect(screen.queryByText('ZZT question')).toBeNull());
    const fresh = [
      { id: 'n1', role: 'user', content: 'ZZT hello new', metadata_json: {}, created_at: '2026-10-30T11:00:00Z' },
      { id: 'n2', role: 'assistant', content: 'ZZT NEW CHAT REPLY', metadata_json: {}, created_at: '2026-10-30T11:00:05Z' },
    ];
    vi.mocked(chatApi.sendAIAssistantMessage).mockResolvedValueOnce({ id: 'conv-new', messages: fresh } as never);

    typeAndSend('ZZT hello new');

    await waitFor(() => expect(screen.getByText('ZZT NEW CHAT REPLY')).toBeDefined());
    vi.mocked(chatApi.sendAIAssistantMessage).mockResolvedValueOnce({ id: 'conv-new', messages: fresh } as never);
    typeAndSend('ZZT again');
    await waitFor(() => expect(vi.mocked(chatApi.sendAIAssistantMessage).mock.calls.length).toBe(2));
    expect(vi.mocked(chatApi.sendAIAssistantMessage).mock.calls[0][1]).toBeUndefined();
    expect(vi.mocked(chatApi.sendAIAssistantMessage).mock.calls[1][1]).toBe('conv-new');
  });
});

describe('AIAssistantBubble: the decision latch and older reloads (review round 2)', () => {
  const stillWaiting = () => [user(), brain({}, { agent: { ...FULL_AGENT, pending_action: PENDING } }, 'm-prop')];

  it('lets a second decision through after the first finished', async () => {
    grant();
    await openThread(stillWaiting());
    vi.mocked(chatApi.confirmPanelAction).mockResolvedValue(OUTCOME as never);
    nextThread(stillWaiting());
    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));
    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(2));
    await act(async () => { await Promise.resolve(); });
    nextThread(stillWaiting());

    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));

    await waitFor(() => expect(chatApi.confirmPanelAction).toHaveBeenCalledTimes(2));
  });

  it('lets a second decision through after the first one failed', async () => {
    grant();
    await openThread(stillWaiting());
    vi.mocked(chatApi.confirmPanelAction).mockRejectedValueOnce(new Error('ZZT refused')).mockResolvedValueOnce(OUTCOME as never);
    nextThread(stillWaiting());
    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(2));
    await act(async () => { await Promise.resolve(); });
    nextThread(stillWaiting());

    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));

    await waitFor(() => expect(chatApi.confirmPanelAction).toHaveBeenCalledTimes(2));
  });

  it('does not let a reload that returns while a send is out overwrite the message just drawn', async () => {
    grant();
    await openThread(stillWaiting());
    vi.mocked(chatApi.confirmPanelAction).mockResolvedValueOnce(OUTCOME as never);
    const reload = deferred<unknown>();
    vi.mocked(chatApi.loadConversation).mockReturnValueOnce(reload.promise as never);
    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));
    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(2));
    const sending = deferred<unknown>();
    vi.mocked(chatApi.sendAIAssistantMessage).mockReturnValueOnce(sending.promise as never);
    typeAndSend('ZZT typed while reloading');
    await waitFor(() => expect(screen.getByText('ZZT typed while reloading')).toBeDefined());

    reload.resolve({ id: 'conv-1', title: null, created_at: '', updated_at: '', messages: stillWaiting() });

    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText('ZZT typed while reloading')).toBeDefined();
    sending.resolve({ id: 'conv-1', messages: stillWaiting() });
    await act(async () => { await Promise.resolve(); });
  });
});

// ---------------------------------------------------------------------------
// AGENTIC-UNIFY PR 3, review round 3: a new thread reopened during its first turn, and the draw counter.
// ---------------------------------------------------------------------------

async function pickFromHistory(id: string, title: string, messages: unknown[]) {
  if (!screen.queryByLabelText('Show conversation history')) throw new Error('no history button');
  vi.mocked(chatApi.listAIAssistantConversations).mockResolvedValueOnce({
    items: [{ id, title, updated_at: '2026-10-30T10:00:05Z' }],
  } as never);
  fireEvent.click(screen.getByLabelText('Show conversation history'));
  const row = await screen.findByText(title);
  vi.mocked(chatApi.loadConversation).mockResolvedValueOnce({ id, title: null, created_at: '', updated_at: '', messages } as never);
  fireEvent.click(row);
  await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.at(-1)?.[0]).toBe(id));
  await act(async () => { await Promise.resolve(); });
}

const NEW_THREAD_SO_FAR = [
  { id: 'n1', role: 'user', content: 'ZZT first message', metadata_json: {}, created_at: '2026-10-30T11:00:00Z' },
];
const NEW_THREAD_DONE = [
  ...NEW_THREAD_SO_FAR,
  { id: 'n2', role: 'assistant', content: 'ZZT FIRST TURN REPLY', metadata_json: {}, created_at: '2026-10-30T11:00:05Z' },
];

async function startOnNewChat() {
  grant();
  await openThread(proposingThread());
  fireEvent.click(screen.getByLabelText('Start new conversation'));
  await waitFor(() => expect(screen.queryByText('ZZT question')).toBeNull());
  const sending = deferred<unknown>();
  vi.mocked(chatApi.sendAIAssistantMessage).mockReturnValueOnce(sending.promise as never);
  typeAndSend('ZZT first message');
  await waitFor(() => expect(chatApi.sendAIAssistantMessage).toHaveBeenCalled());
  return sending;
}

describe('AIAssistantBubble: a new thread reopened while its first turn runs (review round 3)', () => {
  it('draws the reply when the user picks that new thread from history before it arrives', async () => {
    const sending = await startOnNewChat();
    await pickFromHistory('conv-new', 'ZZT new thread', NEW_THREAD_SO_FAR);

    sending.resolve({ id: 'conv-new', messages: NEW_THREAD_DONE });

    await waitFor(() => expect(screen.getByText('ZZT FIRST TURN REPLY')).toBeDefined());
  });

  it('draws it too when an old thread was picked first, then the new one', async () => {
    const sending = await startOnNewChat();
    await pickFromHistory('conv-2', 'ZZT old thread', otherThread());
    await pickFromHistory('conv-new', 'ZZT new thread', NEW_THREAD_SO_FAR);

    sending.resolve({ id: 'conv-new', messages: NEW_THREAD_DONE });

    await waitFor(() => expect(screen.getByText('ZZT FIRST TURN REPLY')).toBeDefined());
  });

  it('control: with an unrelated old thread picked, the reply is dropped and the old thread keeps its id', async () => {
    const sending = await startOnNewChat();
    await pickFromHistory('conv-2', 'ZZT old thread', otherThread());

    sending.resolve({ id: 'conv-new', messages: NEW_THREAD_DONE });
    await act(async () => { await Promise.resolve(); });

    expect(screen.queryByText('ZZT FIRST TURN REPLY')).toBeNull();
    expect(screen.getByText('ZZT other answer')).toBeDefined();
    vi.mocked(chatApi.sendAIAssistantMessage).mockResolvedValueOnce({ id: 'conv-2', messages: otherThread() } as never);
    typeAndSend('ZZT next');
    await waitFor(() => expect(vi.mocked(chatApi.sendAIAssistantMessage).mock.calls.length).toBe(2));
    expect(vi.mocked(chatApi.sendAIAssistantMessage).mock.calls[1][1]).toBe('conv-2');
  });
});

describe('AIAssistantBubble: kill gaps on a failed send and on the draw counter (review round 3)', () => {
  it('a failed send while another thread is open draws no error bubble there', async () => {
    grant();
    await openThread(proposingThread());
    const sending = deferred<unknown>();
    vi.mocked(chatApi.sendAIAssistantMessage).mockReturnValueOnce(sending.promise as never);
    typeAndSend('ZZT on thread A');
    await waitFor(() => expect(chatApi.sendAIAssistantMessage).toHaveBeenCalled());
    await pickOtherThread();

    sending.reject(new Error('ZZT WRONG THREAD ERROR'));
    await act(async () => { await Promise.resolve(); });

    expect(screen.queryByText('ZZT WRONG THREAD ERROR')).toBeNull();
    expect(screen.getByText('ZZT other answer')).toBeDefined();
  });

  it('a reload started before the same thread was picked again is dropped when it returns', async () => {
    grant();
    await openThread(proposingThread());
    vi.mocked(chatApi.confirmPanelAction).mockResolvedValueOnce(OUTCOME as never);
    const reload = deferred<unknown>();
    vi.mocked(chatApi.loadConversation).mockReturnValueOnce(reload.promise as never);
    fireEvent.click(within(screen.getByTestId('agent-proposal')).getByRole('button', { name: /Confirm/ }));
    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(2));
    // the same thread is picked again from history and draws the decided state
    const decidedNow = [user(), brain({}, { agent: { pending_action: null, actions: [] } }, 'm-prop')];
    await pickFromHistory('conv-1', 'ZZT same thread', decidedNow);
    await waitFor(() => expect(screen.queryByTestId('agent-proposal')).toBeNull());

    reload.resolve({ id: 'conv-1', title: null, created_at: '', updated_at: '', messages: proposingThread() });
    await act(async () => { await Promise.resolve(); });

    expect(screen.queryByTestId('agent-proposal')).toBeNull();
  });

  it('a reload started during a send is dropped once the send has drawn its answer', async () => {
    grant();
    const waiting = () => waitingThread(inAMinute());
    await openThread(waiting());
    const sending = deferred<unknown>();
    vi.mocked(chatApi.sendAIAssistantMessage).mockReturnValueOnce(sending.promise as never);
    typeAndSend('ZZT question two');
    await waitFor(() => expect(chatApi.sendAIAssistantMessage).toHaveBeenCalled());
    vi.mocked(chatApi.withdrawPanelStep).mockResolvedValueOnce({ action_id: ACTION, status: 'executed', reply_text: 'Withdrawn.', steps: [] });
    const reload = deferred<unknown>();
    vi.mocked(chatApi.loadConversation).mockReturnValueOnce(reload.promise as never);
    fireEvent.click(within(screen.getByTestId('agent-step-waiting')).getByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(vi.mocked(chatApi.loadConversation).mock.calls.length).toBe(2));

    sending.resolve({ id: 'conv-1', messages: [...waiting(), { id: 'm-ans', role: 'assistant', content: 'ZZT ANSWER TWO', metadata_json: {}, created_at: '2026-10-30T09:30:00Z' }] });
    await waitFor(() => expect(screen.getByText('ZZT ANSWER TWO')).toBeDefined());
    reload.resolve({ id: 'conv-1', title: null, created_at: '', updated_at: '', messages: waiting() });
    await act(async () => { await Promise.resolve(); });

    expect(screen.getByText('ZZT ANSWER TWO')).toBeDefined();
  });
});
