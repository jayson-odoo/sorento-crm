/**
 * Shared `TurnAttachments` (coder 35, round 2 - moved out of chat-history so the
 * chatbot console can reuse it without duplicating the render). Fixture shape is
 * `engine.py::_clean_attachments`'s own value, measured against
 * `tests/chatbot/test_s3_switch_and_complete_by_body.py` (`{kind: "send_attachments",
 * dry_run, attachments_src: [{url, filename, mimeType, attachmentType, uploadedAt}]}`).
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import { TurnAttachments, extractTurnAttachments, type TurnAttachment } from './TurnAttachments';

afterEach(() => cleanup());

const FILE: TurnAttachment = {
  url: 'https://cdn.example.com/spec.pdf',
  filename: 'SRTWC8517 spec sheet.pdf',
  mimeType: 'application/pdf',
  attachmentType: 'Spec Sheet',
  uploadedAt: '2026-09-01T00:00:00.000Z',
};

describe('TurnAttachments', () => {
  it('renders each attachment: filename link, attachmentType badge, muted mimeType', () => {
    render(<TurnAttachments attachments={[FILE]} />);

    const link = screen.getByRole('link', { name: 'SRTWC8517 spec sheet.pdf' });
    expect(link).toHaveAttribute('href', 'https://cdn.example.com/spec.pdf');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByText('Spec Sheet')).toBeInTheDocument();
    expect(screen.getByText('application/pdf')).toBeInTheDocument();
  });

  it('renders one row per file, in order', () => {
    const files: TurnAttachment[] = [
      { url: 'https://cdn.example.com/a.pdf', filename: 'a.pdf', mimeType: 'application/pdf', attachmentType: 'Certificate' },
      { url: 'https://cdn.example.com/b.jpg', filename: 'b.jpg', mimeType: 'image/jpeg', attachmentType: 'Product Photos' },
    ];
    render(<TurnAttachments attachments={files} />);

    const links = screen.getAllByRole('link');
    expect(links.map((l) => l.textContent)).toEqual(['a.pdf', 'b.jpg']);
  });

  it('is absent when given no attachments', () => {
    const { container } = render(<TurnAttachments attachments={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('extractTurnAttachments', () => {
  it('reads the send_attachments action out of a raw actions[] array', () => {
    const actions = [
      { kind: 'send_message', text: 'Here is the spec sheet.' },
      { kind: 'send_attachments', dry_run: true, attachments_src: [FILE] },
    ];
    expect(extractTurnAttachments(actions)).toEqual([FILE]);
  });

  it('is empty with no send_attachments action', () => {
    expect(extractTurnAttachments([{ kind: 'send_message', text: 'x' }])).toEqual([]);
  });

  it('is empty for null/undefined/non-array input', () => {
    expect(extractTurnAttachments(null)).toEqual([]);
    expect(extractTurnAttachments(undefined)).toEqual([]);
    expect(extractTurnAttachments('not an array')).toEqual([]);
  });

  it('drops entries with no url or filename', () => {
    const actions = [{ kind: 'send_attachments', attachments_src: [{ mimeType: 'x' }] }];
    expect(extractTurnAttachments(actions)).toEqual([]);
  });
});
