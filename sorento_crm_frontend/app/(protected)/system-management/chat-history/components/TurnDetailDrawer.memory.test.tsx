/**
 * B2 (reviewer finding, PR #1304): every turn recorded BEFORE this lane's `level` and
 * `facts_saved` keys existed on the `memory` trace event still has a `memory` section
 * in `trace_detail` - the backend's `_memory()` (`app/services/chatbot/trace_detail.py`)
 * always composes the section, it just reads `None` off a raw entry missing those keys.
 * The pre-lane shape this fixture is built from is exactly what
 * `git show 232182ae:sorento_crm_backend/app/services/chatbot/trace_detail.py` (lines
 * ~273-283) used to return: `{focus, profile, episodes}`, nothing else - `level` is
 * `null` (the key never existed on the raw entry) and `episodes` is `null` for the same
 * reason. Opening Memory in the Chat History drawer on one of these turns threw
 * `TypeError: Cannot read properties of null (reading 'own')` at `memory.level.own`.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';

import { TurnDetailDrawer } from './TurnDetailDrawer';
import type { ChatbotTurnDetail, TurnDetail } from '../types/chatbotTurn.types';

let turnState: { data: ChatbotTurnDetail | undefined; isLoading: boolean; isError: boolean } = {
  data: undefined,
  isLoading: false,
  isError: false,
};

vi.mock('../hooks/useChatbotTurns', () => ({
  useChatbotTurn: () => turnState,
}));

afterEach(() => {
  cleanup();
  turnState = { data: undefined, isLoading: false, isError: false };
});

function emptyDetail(): TurnDetail {
  return {
    stages: [],
    parse: null,
    decay: [],
    open_question: null,
    focus: [],
    tool: null,
    crossdomain: [],
    reveals: { restricted_fields_seen: [], granted: [], dropped: [] },
    session: { before: {}, after: {}, diff: [] },
  };
}

function detailTurn(trace_detail: TurnDetail): ChatbotTurnDetail {
  return {
    id: 'ZZT-turn-pre-lane-1',
    contact_respond_id: 'ZZT-contact-1',
    message_id: 'wamid.zzt.1',
    status: 'done',
    stage: 'sent',
    branch_kind: 'business_query',
    attempt: 1,
    is_test: false,
    created_at: '2026-08-01T00:00:00Z',
    finished_at: '2026-08-01T00:00:02Z',
    trace: [],
    response: null,
    trace_detail,
  };
}

describe('TurnDetailDrawer Memory section - pre-lane turns (B2)', () => {
  it('renders without throwing when the backend sends level: null and episodes: null, the exact shape a turn recorded before this lane still gets', () => {
    const detail = emptyDetail();
    // The exact `_memory()` output for a pre-lane turn: `level` and `episodes` are
    // `None` (the raw trace entry never had those keys), `facts_saved` defaults to
    // `[]` (backend already does `entry.get("facts_saved") or []`).
    detail.memory = {
      level: null,
      focus: { before: null, after: { domains: ['order'] }, writer: null },
      profile: { before: {}, after: {}, writer: null },
      episodes: null,
      facts_saved: [],
    };
    turnState = { data: detailTurn(detail), isLoading: false, isError: false };

    expect(() =>
      render(<TurnDetailDrawer turnId="ZZT-turn-pre-lane-1" onOpenChange={vi.fn()} />),
    ).not.toThrow();

    fireEvent.click(screen.getByTestId('section-memory-trigger'));
    const panel = screen.getByTestId('section-memory');
    // Falls back to "system default" - there is no own level to show.
    expect(within(panel).getByText('system default')).toBeInTheDocument();
    expect(within(panel).getAllByText('none this turn').length).toBeGreaterThan(0);
  });
});
