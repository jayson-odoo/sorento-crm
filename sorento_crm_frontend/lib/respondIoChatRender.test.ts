import { describe, it, expect } from 'vitest';

import {
  describeMessageAttachments,
  describeQuotedContext,
  extractSelectionOptions,
  extractTemplateButtons,
  fileNameFromAttachmentUrl,
  getMessageBodyText,
  QUOTED_CONTEXT_MAX_CHARS,
  type RespondMessageRenderable,
} from './respondIoChatRender';

function msg(message: RespondMessageRenderable['message']): RespondMessageRenderable {
  return { messageId: 1, traffic: 'incoming', message };
}

// ---------------------------------------------------------------------------
// describeMessageAttachments - UAC AC-D4: every inbound shape gets AT LEAST a
// typed placeholder; unknown types never crash and never render blank.
// ---------------------------------------------------------------------------
describe('describeMessageAttachments', () => {
  it('single object attachment (image) - name falls back to the URL basename (AC-D5)', () => {
    const out = describeMessageAttachments(
      msg({ type: 'attachment', attachment: { type: 'image', url: '/media/photo.jpg' } }),
    );
    expect(out).toEqual([
      { kind: 'image', label: 'Photo', url: '/media/photo.jpg', fileName: 'photo.jpg' },
    ]);
  });

  it('an explicit fileName always wins over the URL basename', () => {
    const out = describeMessageAttachments(
      msg({
        type: 'attachment',
        attachment: {
          type: 'file',
          url: 'https://cdn.test/t/id/uuid/Q3_stock.xlsx',
          fileName: 'Q3 stock.xlsx',
        },
      }),
    );
    expect(out[0].fileName).toBe('Q3 stock.xlsx');
  });

  it('our own uploads surface the clean filename, never the uuid segment (AC-D5)', () => {
    const out = describeMessageAttachments(
      msg({
        type: 'attachment',
        attachment: {
          type: 'file',
          url: 'https://cdn.test/conversation_sla_tracking/biz-1/9f1c8f5e-aaaa-bbbb-cccc-1234567890ab/Q3_stock.xlsx',
        },
      }),
    );
    expect(out[0].fileName).toBe('Q3_stock.xlsx');
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
    // rendering elsewhere) - the important behaviour under test is that this
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
// fileNameFromAttachmentUrl - the URL is the only name channel Respond gives us
// ---------------------------------------------------------------------------
describe('fileNameFromAttachmentUrl', () => {
  it('takes the last path segment', () => {
    expect(fileNameFromAttachmentUrl('https://cdn.test/a/b/DO-2026-0442.pdf')).toBe(
      'DO-2026-0442.pdf',
    );
  });

  it('drops the signed-URL query string and the fragment', () => {
    expect(
      fileNameFromAttachmentUrl('https://cf.test/a/uuid/Q3_stock.xlsx?Expires=1&Signature=x'),
    ).toBe('Q3_stock.xlsx');
    expect(fileNameFromAttachmentUrl('https://cf.test/a/report.pdf#page=2')).toBe('report.pdf');
  });

  it('decodes percent-escapes', () => {
    expect(fileNameFromAttachmentUrl('https://cdn.test/a/%E6%8A%A5%E4%BB%B7%E5%8D%95.pdf')).toBe(
      '报价单.pdf',
    );
  });

  it('keeps the raw segment when the escape is malformed, never throws', () => {
    expect(fileNameFromAttachmentUrl('https://cdn.test/a/100%.pdf')).toBe('100%.pdf');
  });

  it('returns undefined for missing / unusable urls', () => {
    expect(fileNameFromAttachmentUrl(undefined)).toBeUndefined();
    expect(fileNameFromAttachmentUrl('   ')).toBeUndefined();
    expect(fileNameFromAttachmentUrl('https://cdn.test/a/')).toBeUndefined();
  });

  // FINDING 8: Respond-hosted media is named after a uuid or a content hash.
  // Showing that as the filename is worse than the typed label - it is a UUID
  // in the UI, and it tells the reader nothing.
  it('refuses a bare uuid basename, so the typed label is used instead', () => {
    expect(
      fileNameFromAttachmentUrl(
        'https://cdn.respond.io/e2f1c0b8-9a3d-4f21-8c77-2b6e5a9d1234.jpg',
      ),
    ).toBeUndefined();
    expect(
      fileNameFromAttachmentUrl('https://cdn.respond.io/e2f1c0b8-9a3d-4f21-8c77-2b6e5a9d1234'),
    ).toBeUndefined();
  });

  it('refuses a long hex hash basename', () => {
    expect(
      fileNameFromAttachmentUrl(
        'https://cdn.respond.io/9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08.png',
      ),
    ).toBeUndefined();
    expect(fileNameFromAttachmentUrl('https://cdn.respond.io/e2f1c0b89a3d4f218c772b6e5a9d1234')).toBeUndefined();
  });

  it('keeps a real name that merely looks technical', () => {
    expect(fileNameFromAttachmentUrl('https://cf.test/a/DO-2026-0442.pdf')).toBe('DO-2026-0442.pdf');
    expect(fileNameFromAttachmentUrl('https://cf.test/a/abc123.jpg')).toBe('abc123.jpg');
    expect(fileNameFromAttachmentUrl('https://cf.test/a/IMG_20260815.jpg')).toBe('IMG_20260815.jpg');
  });
});

// ---------------------------------------------------------------------------
// describeQuotedContext - UAC AC-L6: the STRUCTURED inbound quote, read from
// Respond's `replyTo`, never parsed out of the body.
// ---------------------------------------------------------------------------

describe('describeQuotedContext', () => {
  it('reads the quoted id, excerpt and direction', () => {
    expect(
      describeQuotedContext({
        messageId: 2,
        traffic: 'incoming',
        message: { type: 'text', text: 'which one?' },
        replyTo: {
          messageId: 1,
          traffic: 'outgoing',
          message: { type: 'text', text: 'Your order ships Tuesday.' },
        },
      }),
    ).toEqual({ messageId: '1', excerpt: 'Your order ships Tuesday.', sender: 'agent' });
  });

  it('normalizes whitespace so a multi-line quote stays one readable line', () => {
    expect(
      describeQuotedContext({
        replyTo: { messageId: '9', message: { text: ' line one \n\n line two  ' } },
      })?.excerpt,
    ).toBe('line one line two');
  });

  it('a quoted quick_reply reads its prose off `title`, never "[quick_reply]"', () => {
    expect(
      describeQuotedContext({
        replyTo: {
          messageId: 7,
          traffic: 'outgoing',
          message: { type: 'quick_reply', title: 'Escalate this?', replies: ['Yes escalate', 'No'] },
        },
      }),
    ).toEqual({ messageId: '7', excerpt: 'Escalate this?', sender: 'agent' });
  });

  it('a quoted quick_reply with no title shows its options', () => {
    expect(
      describeQuotedContext({
        replyTo: { messageId: 7, message: { type: 'quick_reply', replies: ['Yes escalate', 'No'] } },
      })?.excerpt,
    ).toBe('Yes escalate | No');
  });

  it('falls back to a typed placeholder for a quoted media message', () => {
    expect(
      describeQuotedContext({ replyTo: { messageId: 5, message: { type: 'image' } } }),
    ).toEqual({ messageId: '5', excerpt: '[image]', sender: null });
  });

  it('still says something when only the quoted id is known', () => {
    expect(describeQuotedContext({ replyTo: { messageId: 5 } })?.excerpt).toBe('Quoted message');
  });

  it('clips a very long excerpt', () => {
    const long = 'x'.repeat(QUOTED_CONTEXT_MAX_CHARS + 40);
    const out = describeQuotedContext({ replyTo: { messageId: 5, message: { text: long } } });
    expect(out?.excerpt.length).toBeLessThanOrEqual(QUOTED_CONTEXT_MAX_CHARS + 1);
    expect(out?.excerpt.endsWith('…')).toBe(true);
  });

  it('is null for a message with no quote, and for an empty / malformed one', () => {
    expect(describeQuotedContext(msg({ type: 'text', text: 'hi' }))).toBeNull();
    expect(describeQuotedContext({ replyTo: null })).toBeNull();
    expect(describeQuotedContext({ replyTo: {} })).toBeNull();
    expect(describeQuotedContext({ replyTo: { messageId: '  ' } })).toBeNull();
  });

  it('a literal ">" in the body is never read as a quote (no outbound emulation exists)', () => {
    const item: RespondMessageRenderable = {
      traffic: 'outgoing',
      message: { type: 'text', text: '> quoted line\nreply body' },
    };
    expect(describeQuotedContext(item)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// The interactive shapes Respond.io actually sends. Every fixture below is
// copied from a live message in this workspace's own history - the reason the
// old guesses (quickReplies / options / buttons) never fired is that Respond
// uses neither of those keys.
// ---------------------------------------------------------------------------
describe('getMessageBodyText', () => {
  it('reads a plain message body', () => {
    expect(getMessageBodyText(msg({ type: 'text', text: 'no stock today' }))).toBe(
      'no stock today',
    );
  });

  it('reads a quick_reply body off `title`', () => {
    const out = getMessageBodyText(
      msg({
        type: 'quick_reply',
        title: 'No stock for SRTW2600-SS-CR. Reply with a code to continue.',
        replies: ['SRTW2600', 'Yes escalate'],
      }),
    );
    expect(out).toBe('No stock for SRTW2600-SS-CR. Reply with a code to continue.');
  });

  it('prefers a non-empty text over title', () => {
    expect(getMessageBodyText(msg({ type: 'text', text: 'body', title: 'other' }))).toBe('body');
  });

  it('is empty for a message carrying neither', () => {
    expect(getMessageBodyText(msg({ type: 'attachment' }))).toBe('');
  });
});

describe('extractSelectionOptions - quick_reply', () => {
  it('reads the bare `replies` strings a quick_reply carries', () => {
    const out = extractSelectionOptions(
      msg({
        type: 'quick_reply',
        title: 'Try one of these',
        replies: ['SRTFC2043', 'SRTFC2044', 'Yes escalate', "No it's okay"],
      }),
    );
    expect(out).toEqual(['SRTFC2043', 'SRTFC2044', 'Yes escalate', "No it's okay"]);
  });

  it('still reads the older object-shaped keys', () => {
    const out = extractSelectionOptions(
      msg({ type: 'quick_reply', quickReplies: [{ title: 'Yes' }, 'No'] }),
    );
    expect(out).toEqual(['Yes', 'No']);
  });
});

describe('extractTemplateButtons', () => {
  const template = (components: unknown) =>
    msg({ type: 'whatsapp_template', text: 'body', template: { components } } as never);

  it('reads a url button off a whatsapp template', () => {
    const out = extractTemplateButtons(
      template([
        { type: 'body', text: '*Complaint No - CMP26-0181*' },
        {
          type: 'buttons',
          buttons: [
            {
              type: 'url',
              text: 'View',
              url: 'https://fe-sorento.foundryx.my/portal/c/VWRW980G6B/complaint/3f871885',
            },
          ],
        },
      ]),
    );
    expect(out).toEqual([
      {
        text: 'View',
        url: 'https://fe-sorento.foundryx.my/portal/c/VWRW980G6B/complaint/3f871885',
      },
    ]);
  });

  it('keeps a button with no url as a bare label', () => {
    const out = extractTemplateButtons(
      template([{ type: 'buttons', buttons: [{ type: 'quick_reply', text: 'Stop' }] }]),
    );
    expect(out).toEqual([{ text: 'Stop' }]);
  });

  it('drops a nameless button and returns nothing for a plain message', () => {
    expect(
      extractTemplateButtons(template([{ type: 'buttons', buttons: [{ type: 'url', url: 'x' }] }])),
    ).toEqual([]);
    expect(extractTemplateButtons(msg({ type: 'text', text: 'hi' }))).toEqual([]);
  });
});
