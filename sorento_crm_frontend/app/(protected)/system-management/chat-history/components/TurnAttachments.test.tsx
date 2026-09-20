/**
 * The `send_attachments` action, rendered under a bot reply (coder 35, CI reds + console
 * follow-up). Fixture shape is `engine.py::_clean_attachments`'s own value, measured
 * against `tests/chatbot/test_s3_switch_and_complete_by_body.py` (`{kind:
 * "send_attachments", dry_run, attachments_src: [{url, filename, mimeType,
 * attachmentType, uploadedAt}]}`).
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import { TurnAttachments } from './TurnAttachments';
import type { ChatbotTurn } from '../types/chatbotTurn.types';

afterEach(() => cleanup());

function turn(over: Partial<ChatbotTurn> = {}): ChatbotTurn {
  return {
    id: 'ZZT-turn-0001',
    contact_respond_id: 'ZZT-contact-0001',
    message_id: 'wamid.zzt.0001',
    status: 'done',
    stage: 'sent',
    branch_kind: 'business_query',
    attempt: 1,
    is_test: false,
    created_at: '2026-09-20T06:00:00.000Z',
    finished_at: '2026-09-20T06:00:04.000Z',
    trace: [],
    response: { reply: { text: 'Here is the spec sheet.' } },
    ...over,
  };
}

describe('TurnAttachments', () => {
  it('renders each attachment: filename link, attachmentType badge, muted mimeType', () => {
    render(
      <TurnAttachments
        turn={turn({
          response: {
            reply: { text: 'Here is the spec sheet.' },
            actions: [
              { kind: 'send_message', text: 'Here is the spec sheet.' },
              {
                kind: 'send_attachments',
                dry_run: true,
                attachments_src: [
                  {
                    url: 'https://cdn.example.com/spec.pdf',
                    filename: 'SRTWC8517 spec sheet.pdf',
                    mimeType: 'application/pdf',
                    attachmentType: 'Spec Sheet',
                    uploadedAt: '2026-09-01T00:00:00.000Z',
                  },
                ],
              },
            ],
          },
        })}
      />,
    );

    const link = screen.getByRole('link', { name: 'SRTWC8517 spec sheet.pdf' });
    expect(link).toHaveAttribute('href', 'https://cdn.example.com/spec.pdf');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByText('Spec Sheet')).toBeInTheDocument();
    expect(screen.getByText('application/pdf')).toBeInTheDocument();
  });

  it('renders one row per file, in order', () => {
    render(
      <TurnAttachments
        turn={turn({
          response: {
            reply: { text: 'Two files.' },
            actions: [
              {
                kind: 'send_attachments',
                attachments_src: [
                  {
                    url: 'https://cdn.example.com/a.pdf',
                    filename: 'a.pdf',
                    mimeType: 'application/pdf',
                    attachmentType: 'Certificate',
                  },
                  {
                    url: 'https://cdn.example.com/b.jpg',
                    filename: 'b.jpg',
                    mimeType: 'image/jpeg',
                    attachmentType: 'Product Photos',
                  },
                ],
              },
            ],
          },
        })}
      />,
    );

    const links = screen.getAllByRole('link');
    expect(links.map((l) => l.textContent)).toEqual(['a.pdf', 'b.jpg']);
  });

  it('is absent when the turn has no send_attachments action', () => {
    const { container } = render(
      <TurnAttachments
        turn={turn({
          response: {
            reply: { text: 'Stock is 12 on hand.' },
            actions: [{ kind: 'send_message', text: 'Stock is 12 on hand.' }],
          },
        })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('is absent when the turn has no response at all', () => {
    const { container } = render(<TurnAttachments turn={turn({ response: null })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('is absent when attachments_src has no entries with a url and filename', () => {
    const { container } = render(
      <TurnAttachments
        turn={turn({
          response: {
            reply: { text: 'x' },
            actions: [{ kind: 'send_attachments', attachments_src: [{ mimeType: 'x' }] }],
          },
        })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
