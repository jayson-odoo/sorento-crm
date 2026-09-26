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

  // #1277 (AC-6/AC-7): offered images ride the same send_attachments action, one
  // per image, captioned with its menu position - the console renders each as a
  // thumbnail with that caption instead of a bare file link.
  it('renders an image entry as a thumbnail with its caption', () => {
    const image = {
      url: 'https://cdn.example.com/mockup.jpg',
      filename: 'mockup.jpg',
      mimeType: 'image/jpeg',
      attachmentType: 'image',
      caption: '1',
    } as TurnAttachment;
    render(<TurnAttachments attachments={[image]} />);

    const img = screen.getByRole('img');
    expect(img).toHaveAttribute('src', 'https://cdn.example.com/mockup.jpg');
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('renders a non-image entry as a link, no <img>, as today', () => {
    render(<TurnAttachments attachments={[FILE]} />);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: FILE.filename })).toBeInTheDocument();
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

  // #1277: `caption` (the menu position, e.g. "1") must survive extraction so the
  // render side can show it under the thumbnail.
  it('keeps caption on the extracted entry', () => {
    const actions = [
      { kind: 'send_attachments', attachments_src: [{ ...FILE, caption: '1' }] },
    ];
    const [entry] = extractTurnAttachments(actions);
    expect((entry as unknown as { caption?: string }).caption).toBe('1');
  });
});
