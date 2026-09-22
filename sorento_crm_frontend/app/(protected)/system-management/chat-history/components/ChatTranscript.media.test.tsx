/**
 * S1/S4 (PLAN-chatbot-media-into-turn.md): the incoming-message media block in Chat
 * History - image thumbnail, audio player + transcript, "Read N items" chip, denial
 * plain-bubble.
 *
 * AC-1842, AC-1843, AC-1844, AC-1845, AC-1846, AC-1849 (UAC section E).
 *
 * `ChatbotTurn.media` (`types/chatbotTurn.types.ts::ChatbotTurnMedia`) now ships for
 * real (coder, S1/S4) - fixtures below use the real type directly rather than the
 * tester's original intersection cast, which clashed with it (`entities` is
 * `Array<{raw, hint?, confident?}>`, not `string[]`; fix round, 23 Sep 2026).
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import { ChatTranscript } from './ChatTranscript';
import type { ChatMessageRow } from '../types/chatHistory.types';
import type { ChatbotTurn } from '../types/chatbotTurn.types';

vi.mock('./TurnPanel', () => ({
  TurnPanel: ({ turn }: { turn: ChatbotTurn }) => <div data-testid="turn-panel">{turn.status}</div>,
}));
vi.mock('./StateTracePanel', () => ({ StateTracePanel: () => null }));

afterEach(() => cleanup());

function message(over: Partial<ChatMessageRow>): ChatMessageRow {
  return {
    id: 1,
    contact_id: 'ZZT-contact',
    type: 'incoming',
    message: '',
    sent_at: '2026-09-05T06:00:00.000Z',
    latency_seconds: null,
    delivery_status: null,
    message_id: null,
    turn_id: null,
    state_trace: null,
    ...over,
  } as ChatMessageRow;
}

function turn(over: Partial<ChatbotTurn>): ChatbotTurn {
  return {
    id: 'ZZT-turn',
    contact_respond_id: 'ZZT-contact',
    message_id: null,
    status: 'done',
    stage: 'sent',
    branch_kind: 'business_query',
    attempt: 1,
    is_test: false,
    created_at: '2026-09-05T06:00:00.000Z',
    finished_at: '2026-09-05T06:00:04.000Z',
    trace: [],
    response: { reply: { text: 'I read A and B from that photo.' } },
    media: null,
    ...over,
  };
}

const IMAGE_URL = 'https://cdn.example/chatbot-media/photo.jpg?sig=zzt';
const AUDIO_URL = 'https://cdn.example/chatbot-media/voice.ogg?sig=zzt';

describe('ChatTranscript media block (S1/S4)', () => {
  it('AC-1842: renders an image thumbnail above the caption for an image turn', () => {
    const incoming = message({ id: 1, message_id: 'wamid.photo', message: 'Check stock' });
    const byMessageId = new Map<string, ChatbotTurn>([
      [
        'wamid.photo',
        turn({
          id: 'photo-turn',
          message_id: 'wamid.photo',
          media: {
            modality: 'image',
            mime_type: 'image/jpeg',
            attachment_id: 'att-1',
            url: IMAGE_URL,
            transcript_or_rendered_text: 'Check stock: A, B',
            entities: [{ raw: 'A' }, { raw: 'B' }],
            attributes: [],
            notes: null,
            truncated: false,
            decision: 'accepted',
          },
        }),
      ],
    ]);

    render(<ChatTranscript messages={[incoming]} turnsByMessageId={byMessageId} failedTurnsOnly={false} />);

    const thumb = screen.queryByRole('img', { name: /photo|check stock/i });
    expect(thumb, 'no image thumbnail rendered for an image turn').not.toBeNull();
    expect((thumb as HTMLImageElement)?.src).toContain('photo.jpg');
  });

  it('AC-1843: clicking the thumbnail opens a lightbox with the same url', () => {
    const incoming = message({ id: 1, message_id: 'wamid.photo2' });
    const byMessageId = new Map<string, ChatbotTurn>([
      [
        'wamid.photo2',
        turn({
          message_id: 'wamid.photo2',
          media: {
            modality: 'image',
            mime_type: 'image/jpeg',
            attachment_id: 'att-2',
            url: IMAGE_URL,
            transcript_or_rendered_text: null,
            entities: [],
            attributes: [],
            notes: null,
            truncated: false,
            decision: 'accepted',
          },
        }),
      ],
    ]);

    render(<ChatTranscript messages={[incoming]} turnsByMessageId={byMessageId} failedTurnsOnly={false} />);

    const thumb = screen.queryByRole('img');
    expect(thumb, 'no thumbnail to click').not.toBeNull();
    fireEvent.click(thumb as HTMLImageElement);

    const dialog = screen.queryByRole('dialog');
    expect(dialog, 'no lightbox opened on thumbnail click').not.toBeNull();
    const enlarged = dialog ? dialog.querySelector(`img[src*="photo.jpg"]`) : null;
    expect(enlarged, 'lightbox does not show the same image url').not.toBeNull();
  });

  it('AC-1844: renders an audio player and the transcript for a voice turn', () => {
    const incoming = message({ id: 2, message_id: 'wamid.voice' });
    const byMessageId = new Map<string, ChatbotTurn>([
      [
        'wamid.voice',
        turn({
          message_id: 'wamid.voice',
          media: {
            modality: 'voice',
            mime_type: 'audio/ogg',
            attachment_id: 'att-3',
            url: AUDIO_URL,
            transcript_or_rendered_text: 'stock for SRTWB1455',
            entities: [{ raw: 'SRTWB1455' }],
            attributes: [],
            notes: null,
            truncated: false,
            decision: 'accepted',
          },
        }),
      ],
    ]);

    const { container } = render(
      <ChatTranscript messages={[incoming]} turnsByMessageId={byMessageId} failedTurnsOnly={false} />,
    );

    const audio = container.querySelector('audio[controls]');
    expect(audio, 'no <audio controls> rendered for a voice turn').not.toBeNull();
    expect(audio?.getAttribute('src')).toBe(AUDIO_URL);
    expect(screen.getByText('stock for SRTWB1455')).toBeInTheDocument();
  });

  it('AC-1845: shows a "Read N items" chip for an image turn, amber when truncated', () => {
    const incoming = message({ id: 3, message_id: 'wamid.chip' });
    const byMessageId = new Map<string, ChatbotTurn>([
      [
        'wamid.chip',
        turn({
          message_id: 'wamid.chip',
          media: {
            modality: 'image',
            mime_type: 'image/jpeg',
            attachment_id: 'att-4',
            url: IMAGE_URL,
            transcript_or_rendered_text: 'A, B, C',
            entities: [{ raw: 'A' }, { raw: 'B' }, { raw: 'C' }],
            attributes: [],
            notes: null,
            truncated: true,
            decision: 'accepted',
          },
        }),
      ],
    ]);

    render(<ChatTranscript messages={[incoming]} turnsByMessageId={byMessageId} failedTurnsOnly={false} />);

    const chip = screen.queryByText(/read 3 items/i);
    expect(chip, 'no "Read N items" chip rendered').not.toBeNull();
    expect(chip?.className || chip?.closest('[class]')?.className || '').toMatch(/amber/i);
  });

  it('AC-1846: a media_denied turn renders the plain reply, no thumbnail, no chip', () => {
    const incoming = message({ id: 4, message_id: 'wamid.denied' });
    const byMessageId = new Map<string, ChatbotTurn>([
      [
        'wamid.denied',
        turn({
          message_id: 'wamid.denied',
          branch_kind: 'business_query',
          response: { reply: { text: 'Photos are not enabled for this number yet.' } },
          media: null,
        }),
      ],
    ]);

    render(<ChatTranscript messages={[incoming]} turnsByMessageId={byMessageId} failedTurnsOnly={false} />);

    expect(screen.queryByRole('img', { name: /photo/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/read \d+ items/i)).not.toBeInTheDocument();
  });

  it('AC-1849: no explanatory copy about the feature appears on screen', () => {
    const incoming = message({ id: 5, message_id: 'wamid.explain' });
    const byMessageId = new Map<string, ChatbotTurn>([
      [
        'wamid.explain',
        turn({
          message_id: 'wamid.explain',
          media: {
            modality: 'image',
            mime_type: 'image/jpeg',
            attachment_id: 'att-5',
            url: IMAGE_URL,
            transcript_or_rendered_text: 'A',
            entities: [{ raw: 'A' }],
            attributes: [],
            notes: null,
            truncated: false,
            decision: 'accepted',
          },
        }),
      ],
    ]);

    render(<ChatTranscript messages={[incoming]} turnsByMessageId={byMessageId} failedTurnsOnly={false} />);

    expect(screen.queryByText(/we (now )?read (your )?photos?/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/this (feature|is a new)/i)).not.toBeInTheDocument();
  });
});
