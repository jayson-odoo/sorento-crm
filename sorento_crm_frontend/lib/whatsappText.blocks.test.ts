/**
 * AGENTIC-UNIFY PR 3, slice 4 (red): `parseWhatsAppBlocks`, the block half of the WhatsApp parser (AC-21).
 *
 * Contract: returns `{ kind: 'text', text }` and `{ kind: 'list', ordered, start, items: string[] }` blocks
 * in the order they appear. A list item starts with `- `, `* `, `• `, `1. ` or `1) `; the marker needs its
 * space, so a `*bold*` line is text. Fenced code stays whole. Items keep their inline markup for the
 * inline parse (`WhatsAppText`).
 */
import { describe, expect, it } from 'vitest';
import { parseWhatsAppBlocks } from './whatsappText';

const list = (items: string[], ordered = false, start = 1) => ({ kind: 'list', ordered, start, items });
const text = (value: string) => ({ kind: 'text', text: value });

describe('parseWhatsAppBlocks: lists', () => {
  it.each([
    ['dash', '- a\n- b'],
    ['asterisk', '* a\n* b'],
    ['bullet', '• a\n• b'],
  ])('reads %s items as one unordered list', (_name, input) => {
    expect(parseWhatsAppBlocks(input)).toEqual([list(['a', 'b'])]);
  });

  it.each([
    ['dot', '1. a\n2. b'],
    ['paren', '1) a\n2) b'],
  ])('reads %s numbering as one ordered list starting at 1', (_name, input) => {
    expect(parseWhatsAppBlocks(input)).toEqual([list(['a', 'b'], true, 1)]);
  });

  it('keeps the number a list starts at', () => {
    expect(parseWhatsAppBlocks('3. c\n4. d')).toEqual([list(['c', 'd'], true, 3)]);
  });

  it('keeps inline markup in an item for the inline parse', () => {
    expect(parseWhatsAppBlocks('- *Alpha* stock: 5\n- _Beta_ out')).toEqual([
      list(['*Alpha* stock: 5', '_Beta_ out']),
    ]);
  });
});

describe('parseWhatsAppBlocks: what is not a list', () => {
  it('reads a *bold* line as text, because the marker needs its space', () => {
    expect(parseWhatsAppBlocks('*bold* line')).toEqual([text('*bold* line')]);
  });

  it('reads a lone *bold* as text', () => {
    expect(parseWhatsAppBlocks('*bold*')).toEqual([text('*bold*')]);
  });

  it('reads an _italic_ line as text', () => {
    expect(parseWhatsAppBlocks('_italic_ line')).toEqual([text('_italic_ line')]);
  });

  it('returns nothing for empty input', () => {
    expect(parseWhatsAppBlocks('')).toEqual([]);
  });

  it('keeps a fenced block holding a list item whole, as text', () => {
    const fenced = '```\n- a\n```';
    const blocks = parseWhatsAppBlocks(fenced);
    expect(blocks.some((b) => b.kind === 'list')).toBe(false);
    expect(blocks).toEqual([text(fenced)]);
  });
});

describe('parseWhatsAppBlocks: order and spacing', () => {
  it('keeps text before, between and after lists in order', () => {
    const blocks = parseWhatsAppBlocks('Before\n- a\n- b\nMiddle\n1. x\n2. y\nAfter');
    expect(blocks).toEqual([
      text('Before'),
      list(['a', 'b']),
      text('Middle'),
      list(['x', 'y'], true, 1),
      text('After'),
    ]);
  });

  it('keeps a blank line between text lines as typed', () => {
    expect(parseWhatsAppBlocks('one\n\ntwo')).toEqual([text('one\n\ntwo')]);
  });

  it('keeps consecutive text lines together with their line breaks', () => {
    expect(parseWhatsAppBlocks('line one\nline two')).toEqual([text('line one\nline two')]);
  });
});
