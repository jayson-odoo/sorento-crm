import { describe, expect, it } from 'vitest';

import {
  parseWhatsAppText,
  stripWhatsAppMarkup,
  type WhatsAppTextSegment,
} from './whatsappText';

/** The visible text, so a test can assert nothing was dropped or duplicated. */
const flatten = (segments: WhatsAppTextSegment[]) => segments.map((s) => s.text).join('');
const styled = (segments: WhatsAppTextSegment[], key: keyof WhatsAppTextSegment) =>
  segments.filter((s) => s[key]).map((s) => s.text);

describe('parseWhatsAppText', () => {
  it('returns nothing for empty input', () => {
    expect(parseWhatsAppText('')).toEqual([]);
  });

  it('leaves plain text as one segment', () => {
    expect(parseWhatsAppText('no stock today')).toEqual([{ text: 'no stock today' }]);
  });

  it('marks *bold*, _italic_ and ~strike~ and drops the markers', () => {
    const segments = parseWhatsAppText('a *b* c _d_ e ~f~');
    expect(flatten(segments)).toBe('a b c d e f');
    expect(styled(segments, 'bold')).toEqual(['b']);
    expect(styled(segments, 'italic')).toEqual(['d']);
    expect(styled(segments, 'strike')).toEqual(['f']);
  });

  it('composes nested marks onto one segment', () => {
    const segments = parseWhatsAppText('*_both_*');
    expect(segments).toEqual([{ text: 'both', bold: true, italic: true }]);
  });

  // The regression this whole rule exists for: a promotion name carrying an
  // underscore must not italicise the rest of the message.
  it('ignores markers inside a word', () => {
    const text = 'UPDATED SORENTO STOP VALVE PROMO_07052026 DEALER and CODE_12345 too';
    expect(parseWhatsAppText(text)).toEqual([{ text }]);
  });

  it('formats a real stock-availability reply', () => {
    const text =
      '1. *Product Code:* SRTFC2032\n*Container:* TCNU1214770\n\n_Data last updated: 14/05/2026_';
    const segments = parseWhatsAppText(text);
    expect(flatten(segments)).toBe(
      '1. Product Code: SRTFC2032\nContainer: TCNU1214770\n\nData last updated: 14/05/2026',
    );
    expect(styled(segments, 'bold')).toEqual(['Product Code:', 'Container:']);
    expect(styled(segments, 'italic')).toEqual(['Data last updated: 14/05/2026']);
  });

  it('bolds a parenthesised run', () => {
    const segments = parseWhatsAppText('304 *(PENDING ALLOCATION)*\nnext line');
    expect(styled(segments, 'bold')).toEqual(['(PENDING ALLOCATION)']);
  });

  it('keeps a triple-backtick block literal', () => {
    const segments = parseWhatsAppText('see ```*not bold* https://x.test``` end');
    expect(segments).toEqual([
      { text: 'see ' },
      { text: '*not bold* https://x.test', code: true },
      { text: ' end' },
    ]);
  });

  describe('links', () => {
    it('linkifies an http url', () => {
      const segments = parseWhatsAppText('open https://fe-sorento.foundryx.my/portal/c/AB12 now');
      expect(segments[1]).toEqual({
        text: 'https://fe-sorento.foundryx.my/portal/c/AB12',
        href: 'https://fe-sorento.foundryx.my/portal/c/AB12',
      });
    });

    it('gives a bare www host an https scheme', () => {
      const [segment] = parseWhatsAppText('www.sorento.com.my');
      expect(segment).toEqual({ text: 'www.sorento.com.my', href: 'https://www.sorento.com.my' });
    });

    it('leaves trailing sentence punctuation out of the href', () => {
      const segments = parseWhatsAppText('see https://x.test/a.');
      expect(segments[1].href).toBe('https://x.test/a');
      expect(segments[2]).toEqual({ text: '.' });
    });

    it('carries marks onto a link inside a styled run', () => {
      const [segment] = parseWhatsAppText('*https://x.test/a*');
      expect(segment).toEqual({ text: 'https://x.test/a', href: 'https://x.test/a', bold: true });
    });

    it('does not linkify inside a code block', () => {
      const segments = parseWhatsAppText('```https://x.test```');
      expect(segments).toEqual([{ text: 'https://x.test', code: true }]);
    });
  });

  it('never loses characters from a message with no valid markers', () => {
    const text = 'price is 3*4 and a_b and ~ alone';
    expect(flatten(parseWhatsAppText(text))).toBe(text);
  });
});

describe('stripWhatsAppMarkup', () => {
  it('drops the markers and keeps every word', () => {
    expect(stripWhatsAppMarkup('*Product Code:* SRTFC2032 _updated_')).toBe(
      'Product Code: SRTFC2032 updated',
    );
  });

  it('leaves an url in place as text', () => {
    expect(stripWhatsAppMarkup('open https://x.test/a now')).toBe('open https://x.test/a now');
  });

  it('is empty for empty input', () => {
    expect(stripWhatsAppMarkup('')).toBe('');
  });
});
