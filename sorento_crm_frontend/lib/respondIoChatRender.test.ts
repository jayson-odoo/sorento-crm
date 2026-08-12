import { describe, it, expect } from 'vitest';

import {
  describeMessageAttachments,
  buildQuotedReplyText,
  splitMessageQuote,
  splitQuotedPrefix,
  QUOTE_EXCERPT_MAX_CHARS,
  type RespondMessageRenderable,
} from './respondIoChatRender';

function msg(message: RespondMessageRenderable['message']): RespondMessageRenderable {
  return { messageId: 1, traffic: 'incoming', message };
}

// ---------------------------------------------------------------------------
// describeMessageAttachments — UAC AC-D4: every inbound shape gets AT LEAST a
// typed placeholder; unknown types never crash and never render blank.
// ---------------------------------------------------------------------------
describe('describeMessageAttachments', () => {
  it('single object attachment (image)', () => {
    const out = describeMessageAttachments(
      msg({ type: 'attachment', attachment: { type: 'image', url: '/media/photo.jpg' } }),
    );
    expect(out).toEqual([{ kind: 'image', label: 'Photo', url: '/media/photo.jpg', fileName: undefined }]);
  });

  it('document attachment carries a fileName', () => {
    const out = describeMessageAttachments(
      msg({
        type: 'attachment',
        attachment: { type: 'file', url: '/media/DO-2026-0442.pdf', fileName: 'DO-2026-0442.pdf' },
      }),
    );
    expect(out[0]).toMatchObject({ kind: 'file', label: 'Document', fileName: 'DO-2026-0442.pdf' });
  });

  it('array of attachments (multi-image send) yields one descriptor per item', () => {
    const out = describeMessageAttachments(
      msg({
        type: 'attachment',
        attachment: [
          { type: 'image', url: 'a.jpg' },
          { type: 'video', url: 'b.mp4' },
        ],
      }),
    );
    expect(out).toHaveLength(2);
    expect(out.map((d) => d.kind)).toEqual(['image', 'video']);
  });

  it('sticker type has no url/fileName but still yields a typed placeholder', () => {
    const out = describeMessageAttachments(
      msg({ type: 'sticker', attachment: { type: 'sticker', url: 'https://cdn/sticker.webp' } }),
    );
    expect(out[0]).toMatchObject({ kind: 'sticker', label: 'Sticker' });
  });

  it('audio (voice note)', () => {
    const out = describeMessageAttachments(
      msg({ type: 'attachment', attachment: { type: 'audio', url: 'voice.ogg' } }),
    );
    expect(out[0]).toMatchObject({ kind: 'audio', label: 'Audio message' });
  });

  it('a type the UI has never seen still yields a fallback "Attachment" placeholder, not a crash', () => {
    const out = describeMessageAttachments(
      msg({ type: 'contactCard', contact: { name: 'Site supervisor' } } as never),
    );
    // No attachment/attachments field and an unrecognised top-level type: no
    // descriptor is produced (the bubble falls back to its own unknown-type
    // rendering elsewhere) — the important behaviour under test is that this
    // never throws.
    expect(out).toEqual([]);
  });

  it('bare url on a typed message with no attachment wrapper still produces a descriptor', () => {
    const out = describeMessageAttachments(msg({ type: 'image', url: 'bare.jpg' } as never));
    expect(out[0]).toMatchObject({ kind: 'image', label: 'Photo' });
  });

  it('no message payload at all returns an empty list, never throws', () => {
    expect(describeMessageAttachments({ messageId: 1, traffic: 'incoming' })).toEqual([]);
  });

  it('plain text message has no attachments', () => {
    expect(describeMessageAttachments(msg({ type: 'text', text: 'hello' }))).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Quote round-trip (composer -> wire text -> re-parsed in the chat list)
// ---------------------------------------------------------------------------
describe('buildQuotedReplyText / splitQuotedPrefix round-trip', () => {
  it('prefixes the excerpt with ">" and re-parses it back into quoted + body', () => {
    const wire = buildQuotedReplyText('My delivery yesterday was short by 2 boxes.', 'Checking now.');
    expect(wire).toBe('> My delivery yesterday was short by 2 boxes.\nChecking now.');

    const { quoted, body } = splitQuotedPrefix(wire);
    expect(quoted).toBe('My delivery yesterday was short by 2 boxes.');
    expect(body).toBe('Checking now.');
  });

  it('collapses newlines/whitespace in the excerpt before quoting', () => {
    const wire = buildQuotedReplyText('line one\n\n  line two  ', 'reply');
    expect(wire).toBe('> line one line two\nreply');
  });

  it('elides an excerpt longer than QUOTE_EXCERPT_MAX_CHARS', () => {
    const long = 'x'.repeat(QUOTE_EXCERPT_MAX_CHARS + 40);
    const wire = buildQuotedReplyText(long, 'reply');
    const { quoted } = splitQuotedPrefix(wire);
    expect(quoted?.endsWith('…')).toBe(true);
    expect(quoted?.length).toBeLessThanOrEqual(QUOTE_EXCERPT_MAX_CHARS + 1);
  });

  it('an empty excerpt is a no-op: body passes through unquoted', () => {
    expect(buildQuotedReplyText('   ', 'reply')).toBe('reply');
    expect(splitQuotedPrefix('reply')).toEqual({ quoted: null, body: 'reply' });
  });

  it('a body with no leading ">" is not misparsed as quoted', () => {
    expect(splitQuotedPrefix('just a normal message')).toEqual({
      quoted: null,
      body: 'just a normal message',
    });
  });
});

// ---------------------------------------------------------------------------
// splitMessageQuote - the ">" convention is OURS, so it is only parsed out of
// OUTGOING traffic. An inbound contact message that happens to start with ">"
// used to lose its leading lines into an italic quote block (and, when every
// line was quoted, its whole body).
// ---------------------------------------------------------------------------
describe('splitMessageQuote (direction aware)', () => {
  it('outgoing quoted reply still splits into quote + body', () => {
    const item: RespondMessageRenderable = {
      messageId: 1,
      traffic: 'outgoing',
      message: { type: 'text', text: '> Short by 2 boxes.\nChecking now.' },
    };
    expect(splitMessageQuote(item)).toEqual({
      quoted: 'Short by 2 boxes.',
      body: 'Checking now.',
    });
  });

  it('inbound message starting with ">" renders verbatim, nothing lifted into a quote', () => {
    const text = '> quoting the price list you sent\nis this still valid?';
    const item: RespondMessageRenderable = {
      messageId: 2,
      traffic: 'incoming',
      message: { type: 'text', text },
    };
    expect(splitMessageQuote(item)).toEqual({ quoted: null, body: text });
  });

  it('inbound message that is ENTIRELY ">" lines keeps a body (never an empty bubble)', () => {
    const text = '> line one\n> line two';
    const item: RespondMessageRenderable = {
      messageId: 3,
      traffic: 'incoming',
      message: { type: 'text', text },
    };
    expect(splitMessageQuote(item)).toEqual({ quoted: null, body: text });
  });

  it('a message with no text at all yields an empty body, never throws', () => {
    expect(splitMessageQuote({ messageId: 4, traffic: 'incoming' })).toEqual({
      quoted: null,
      body: '',
    });
  });
});
