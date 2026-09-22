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
  // Review round S5: the REAL shape `engine.py::_media_intake_facts` emits -
  // flattened to what StageRow prints verbatim (a comma-joined `entities` string,
  // no `attributes`/`notes` key at all when there is nothing to say, never the
  // literal word "none"). `job_id`/`attachment_id`/the full `result` live under
  // `raw` instead, which StageRow never reads - so they are absent here too.
  return record({
    // Cast: `media_intake` is not (yet) a member of the `TurnStage` union the type
    // declares - the coder adds it. Cast at the fixture, per the tester brief.
    stage: 'media_intake' as unknown as TurnTraceRecord['stage'],
    summary: 'Read the photo.',
    why: 'The customer sent an image.',
    facts: {
      modality: 'image',
      decision: 'accepted',
      status: 'completed',
      elapsed_ms: 900,
      entities: 'A, B',
    },
    raw: { job_id: 'ZZT-job-1', attachment_id: 'ZZT-attachment-1', result: {} },
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
    expect(screen.queryByText(/A, B/)).not.toBeNull();
    expect(screen.queryByText(/accepted/i)).not.toBeNull();
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
