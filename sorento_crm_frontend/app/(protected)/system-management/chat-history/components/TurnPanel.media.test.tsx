/**
 * S1/S4 (PLAN-chatbot-media-into-turn.md): `TurnPanel` gets one more stage row - "Read
 * the photo" (image) / "Heard the voice note" (voice) - with entities, attributes, notes
 * and the decision, absent on a text turn.
 *
 * AC-1847 (UAC section E).
 *
 * MEASURED FINDING, flagged to the captain rather than assumed: `turnPresentation.ts::
 * stageRecords` is `turn.trace.filter(isStageRecord)` - ANY trace record carrying a
 * `stage` key renders as a timeline row, not only the eight `TURN_STAGES` names.
 * `stageLabel()` falls back to `stage.replace(/_/g, ' ')` for an unknown name, and the
 * row's own `summary`/`facts` render verbatim regardless. So these three tests are
 * **NOT independently red today** - a hand-built `media_intake` trace record with the
 * right `summary`/`facts` already renders correctly through the EXISTING generic
 * component, no frontend change required for AC-1847 itself. What is still missing (and
 * IS covered, red, in the backend suite - `test_media_intake_turn.py`,
 * `test_media_storage_link.py`) is the engine actually PRODUCING that record and the
 * `GET /turns/{id}` projection carrying it. Kept here as the regression guard AC-1847
 * asks for and as the measured proof that no bespoke TurnPanel markup is owed.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { TurnPanel } from './TurnPanel';
import type { ChatbotTurn, TurnTraceRecord } from '../types/chatbotTurn.types';

const retryMutate = vi.fn();

vi.mock('../hooks/useChatbotTurns', () => ({
  useRetryChatbotTurn: () => ({ mutate: retryMutate, isPending: false }),
  useChatbotTurn: () => ({ data: undefined, isLoading: false, isError: false }),
}));

vi.mock('./TurnDetailDrawer', () => ({
  TurnDetailDrawer: () => null,
}));

afterEach(() => cleanup());

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function record(over: Partial<TurnTraceRecord> = {}): TurnTraceRecord {
  return {
    stage: 'received',
    status: 'ok',
    started_at: '2026-09-22T06:00:00.000Z',
    ms: 100,
    summary: 'Received a text message.',
    why: 'Every turn starts here.',
    facts: {},
    error: null,
    raw: {},
    ...over,
  };
}

function mediaIntakeRecord(over: Partial<TurnTraceRecord> = {}): TurnTraceRecord {
  // Copied VERBATIM (browser pass follow-up) from a real `chatbot.turns.trace`
  // row on 0921 (turn 767e0472-2388-47f8-9b40-efef429b45a8, a live console photo
  // turn) rather than hand-typed - the same `facts` shape
  // `engine.py::_media_intake_facts` actually emits: a comma-joined `entities`
  // string, `notes` as free text, no `attributes` key at all when nothing was
  // rescued as an attribute (never the literal word "none"). `job_id`/
  // `attachment_id`/the full extraction `result` live under `raw` instead, which
  // StageRow never reads - so they are exactly as recorded there too.
  return record({
    // Cast: `media_intake` is not (yet) a member of the `TurnStage` union the type
    // declares - the coder adds it. Cast at the fixture, per the tester brief.
    stage: 'media_intake' as unknown as TurnTraceRecord['stage'],
    summary: 'Read the photo.',
    why: 'The customer sent media; this is what the intake pipeline decided and read.',
    facts: {
      notes: 'Simple list of product codes with no quantities or caption.',
      status: 'completed',
      decision: 'accepted',
      entities: 'BRBC22293W-1, SRTWT1506, SRTWT1805',
      modality: 'image',
      elapsed_ms: 72,
    },
    raw: {
      job_id: 'b6ccbbed-b617-4993-bf22-6e930900ba84',
      attachment_id: null,
      result: { rendered_text: 'null: BRBC22293W-1, SRTWT1506, SRTWT1805' },
    },
    ...over,
  });
}

function baseTurn(over: Partial<ChatbotTurn> = {}): ChatbotTurn {
  return {
    id: 'ZZT-turn-media-1',
    contact_respond_id: 'ZZT-contact-media-1',
    message_id: 'wamid.zzt.media.1',
    status: 'done',
    stage: 'sent',
    branch_kind: 'business_query',
    attempt: 1,
    is_test: false,
    created_at: '2026-09-22T06:00:00.000Z',
    finished_at: '2026-09-22T06:00:04.000Z',
    trace: [record({ stage: 'received' }), record({ stage: 'understood' })],
    response: { reply: { text: 'I read A and B from that photo.' } },
    ...over,
  };
}

describe('TurnPanel media stage (AC-1847)', () => {
  it('renders "Read the photo" with entities/attributes/notes/decision for an image turn', () => {
    const turn = baseTurn({
      trace: [record({ stage: 'received' }), mediaIntakeRecord(), record({ stage: 'understood' })],
    });

    renderWithClient(<TurnPanel turn={turn} />);
    // Expand the panel - collapsed by default.
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    const stageTitle = screen.queryByText(/read the photo/i);
    expect(stageTitle, 'no "Read the photo" stage row rendered').not.toBeNull();
    expect(screen.queryByText(/BRBC22293W-1, SRTWT1506, SRTWT1805/)).not.toBeNull();
    expect(screen.queryByText(/accepted/i)).not.toBeNull();
    expect(screen.queryByText(/Simple list of product codes/i)).not.toBeNull();
  });

  it('renders "Heard the voice note" for a voice turn', () => {
    const turn = baseTurn({
      trace: [
        record({ stage: 'received' }),
        mediaIntakeRecord({
          summary: 'Heard the voice note.',
          facts: { modality: 'voice', decision: 'accepted', status: 'completed', elapsed_ms: 400, entities: 'SRTWB1455' },
        }),
        record({ stage: 'understood' }),
      ],
    });

    renderWithClient(<TurnPanel turn={turn} />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    expect(screen.queryByText(/heard the voice note/i)).not.toBeNull();
  });

  it('is absent on a text turn', () => {
    const turn = baseTurn();
    renderWithClient(<TurnPanel turn={turn} />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    expect(screen.queryByText(/read the photo/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/heard the voice note/i)).not.toBeInTheDocument();
  });
});
