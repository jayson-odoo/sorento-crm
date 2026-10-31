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

// Review round 1: each item carries its printed number (`number`, null in an unordered list), because a
// reply of "3" must mean the row marked 3. An item is `{ text, number }`.
type Item = string | [string, number];
const list = (items: Item[], ordered = false, start = 1) => ({
  kind: 'list',
  ordered,
  start,
  items: items.map((item, i) =>
    Array.isArray(item)
      ? { text: item[0], number: item[1] }
      : { text: item, number: ordered ? start + i : null },
  ),
});
const text = (value: string) => ({ kind: 'text', text: value });
/** Text blocks trimmed and the empty ones dropped: where a blank line ends a list is not pinned here. */
const norm = (blocks: ReturnType<typeof parseWhatsAppBlocks>) =>
  blocks
    .map((b) => (b.kind === 'text' ? { ...b, text: b.text.trim() } : b))
    .filter((b) => b.kind !== 'text' || b.text !== '');

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
    const blocks = norm(parseWhatsAppBlocks('Before\n- a\n- b\n\nMiddle\n1. x\n2. y\n\nAfter'));
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

// AGENTIC-UNIFY PR 3, review round 1 (red).
describe('parseWhatsAppBlocks: printed numbers, item lines, marker width (review round 1)', () => {
  it('keeps the printed number of each item when numbering skips', () => {
    const [block] = parseWhatsAppBlocks('1. Alice\n3. Carol');
    expect(block).toEqual(list([['Alice', 1], ['Carol', 3]], true, 1));
  });

  it('keeps a line under an item inside that item until the next marker', () => {
    const blocks = parseWhatsAppBlocks('1. *Code:* A\n*Qty:* 5\n*Loc:* X\n2. *Code:* B');
    expect(blocks).toEqual([list([['*Code:* A\n*Qty:* 5\n*Loc:* X', 1], ['*Code:* B', 2]], true, 1)]);
  });

  it('keeps a line under an unordered item in that item too', () => {
    expect(parseWhatsAppBlocks('- a\nmore of a\n- b')).toEqual([list(['a\nmore of a', 'b'])]);
  });

  it('ends the item at a blank line', () => {
    const blocks = parseWhatsAppBlocks('1. a\n\ntail');
    const lists = blocks.filter((b) => b.kind === 'list');
    expect(lists).toHaveLength(1);
    expect((lists[0] as { items: { text: string }[] }).items.map((i) => i.text)).toEqual(['a']);
    expect(blocks.some((b) => b.kind === 'text' && b.text.includes('tail'))).toBe(true);
  });

  it('control: an item with no line under it is just its own text', () => {
    expect(parseWhatsAppBlocks('1. a\n2. b')).toEqual([list(['a', 'b'], true, 1)]);
  });

  it('reads a four digit year before a dot as text, since an ordered marker is 1 to 3 digits', () => {
    expect(parseWhatsAppBlocks('2026. x')).toEqual([text('2026. x')]);
  });

  it('control: a three digit marker is still a list', () => {
    expect(parseWhatsAppBlocks('123. x')).toEqual([list([['x', 123]], true, 123)]);
  });

  it('keeps a closing fence line whole even when it looks like an item', () => {
    const fenced = '```\ncode\n- end```';
    const blocks = parseWhatsAppBlocks(fenced);
    expect(blocks.some((b) => b.kind === 'list')).toBe(false);
    expect(blocks).toEqual([text(fenced)]);
  });
});
