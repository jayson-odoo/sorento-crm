/**
 * Reply-to wire format (#1317, UAC AC-RT-15/17/20/21).
 *
 * The convention is RECOVERED, not new: `buildQuotedReplyText` /
 * `splitQuotedPrefix` / `splitMessageQuote` as they stood before e313ac690
 * removed them. These cases pin that shape byte for byte.
 */
import { describe, expect, it } from 'vitest';

import {
  QUOTE_EXCERPT_MAX_CHARS,
  QUOTE_LINE_PREFIX,
  buildQuotedReplyText,
  findQuotedOriginal,
  quoteExcerptOf,
  splitMessageQuote,
  splitQuotedPrefix,
  type RespondMessageRenderable,
} from './respondIoChatRender';

function item(over: Partial<RespondMessageRenderable>): RespondMessageRenderable {
  return { messageId: 1, traffic: 'incoming', message: { type: 'text', text: '' }, ...over };
}

describe('buildQuotedReplyText (AC-RT-17)', () => {
  it('puts the excerpt on a "> " line above the body', () => {
    expect(QUOTE_LINE_PREFIX).toBe('> ');
    expect(buildQuotedReplyText('Is the sink in stock?', 'Yes, 3 units.')).toBe(
      '> Is the sink in stock?\nYes, 3 units.',
    );
  });

  it('collapses whitespace so a multi-line quote stays ONE quote line', () => {
    expect(buildQuotedReplyText('  line one\n\nline   two ', 'ok')).toBe('> line one line two\nok');
  });

  it('clips at 160 characters and marks the cut with an ellipsis', () => {
    expect(QUOTE_EXCERPT_MAX_CHARS).toBe(160);
    const long = 'a'.repeat(200);
    const out = buildQuotedReplyText(long, 'body');
    expect(out).toBe(`> ${'a'.repeat(160)}…\nbody`);
  });

  it('returns the body unchanged when there is nothing to quote', () => {
    expect(buildQuotedReplyText('   ', 'body')).toBe('body');
  });
});

describe('splitQuotedPrefix / splitMessageQuote (AC-RT-20)', () => {
  it('round-trips what buildQuotedReplyText wrote', () => {
    const sent = buildQuotedReplyText('Which colour?', 'Matte black.');
    expect(splitQuotedPrefix(sent)).toEqual({ quoted: 'Which colour?', body: 'Matte black.' });
  });

  it('leaves text with no leading ">" alone', () => {
    expect(splitQuotedPrefix('plain')).toEqual({ quoted: null, body: 'plain' });
  });

  it('splits OUTGOING messages only; an inbound ">" line is the contact\'s own words', () => {
    const text = '> quoted\nanswer';
    expect(splitMessageQuote(item({ traffic: 'outgoing', message: { type: 'text', text } }))).toEqual({
      quoted: 'quoted',
      body: 'answer',
    });
    expect(splitMessageQuote(item({ traffic: 'incoming', message: { type: 'text', text } }))).toEqual({
      quoted: null,
      body: text,
    });
  });
});

describe('quoteExcerptOf (AC-RT-15)', () => {
  it('quotes the text when there is some', () => {
    expect(quoteExcerptOf(item({ message: { type: 'text', text: ' hello ' } }))).toBe('hello');
  });

  it('quotes a media message by its placeholder, never an empty line', () => {
    const photo = item({
      message: { type: 'attachment', attachment: { type: 'image', url: 'https://x/p.jpg' } },
    });
    expect(quoteExcerptOf(photo)).toMatch(/^\[image\]/);
    const file = item({
      message: {
        type: 'attachment',
        attachment: { type: 'file', url: 'https://x/quote.pdf', fileName: 'quote.pdf' },
      },
    });
    expect(quoteExcerptOf(file)).toBe('[file] quote.pdf');
  });

  it('falls back to the message type when nothing else is known', () => {
    expect(quoteExcerptOf(item({ message: { type: 'location' } }))).toBe('[location]');
  });

  it('never quotes our own earlier quote line: an outgoing reply is quoted by its body', () => {
    const ours = item({ traffic: 'outgoing', message: { type: 'text', text: '> old\nnew answer' } });
    expect(quoteExcerptOf(ours)).toBe('new answer');
  });
});

describe('findQuotedOriginal (AC-RT-21)', () => {
  const a = item({ messageId: 10, message: { type: 'text', text: 'Is the sink in stock?' } });
  const b = item({ messageId: 20, message: { type: 'text', text: 'And the tap?' } });

  it('finds the earlier message the excerpt was cut from', () => {
    expect(findQuotedOriginal('Is the sink in stock?', [a, b])).toBe(a);
  });

  it('matches a clipped excerpt by its prefix (the ellipsis is ours, not the text)', () => {
    const long = item({ messageId: 30, message: { type: 'text', text: `${'x'.repeat(170)} tail` } });
    const excerpt = splitQuotedPrefix(buildQuotedReplyText(quoteExcerptOf(long), 'r')).quoted!;
    expect(findQuotedOriginal(excerpt, [a, long])).toBe(long);
  });

  it('prefers the NEWEST earlier match when the same words were said twice', () => {
    const again = item({ messageId: 40, message: { type: 'text', text: 'Is the sink in stock?' } });
    expect(findQuotedOriginal('Is the sink in stock?', [a, b, again])).toBe(again);
  });

  it('returns undefined when nothing matches', () => {
    expect(findQuotedOriginal('never said', [a, b])).toBeUndefined();
  });
});
