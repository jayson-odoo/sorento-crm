/**
 * AGENTIC-UNIFY PR 3, slice 4 (red): `WhatsAppBlocks`, a reply drawn as text and real lists (AC-21).
 *
 * Contract: `<WhatsAppBlocks text={...} />` parses with `parseWhatsAppBlocks`, draws a list block as a real
 * `ul`/`ol` with `li` items (the `ol` carries `start`, the list a hanging indent) and everything inline
 * through `WhatsAppText`. `WhatsAppText` itself is untouched (AC-25).
 * Assumed: the hanging indent is a Tailwind start padding class (`ps-N` or `pl-N`) on the list, with
 * `list-disc` / `list-decimal` so the marker draws.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WhatsAppBlocks } from './WhatsAppBlocks';

describe('WhatsAppBlocks', () => {
  it('draws an unordered list as real ul and li elements with a hanging indent', () => {
    const { container } = render(<WhatsAppBlocks text={'Stock:\n- Alpha\n- Beta'} />);
    const ul = container.querySelector('ul');
    expect(ul).not.toBeNull();
    expect(container.querySelector('ol')).toBeNull();
    const items = screen.getAllByRole('listitem');
    expect(items.map((li) => li.textContent)).toEqual(['Alpha', 'Beta']);
    expect(ul!.className).toMatch(/(^|\s)(ps|pl)-\d/);
    expect(ul!.className).toContain('list-disc');
    expect(screen.getByText('Stock:')).toBeDefined();
  });

  it('draws numbering as an ol that carries its start', () => {
    const { container } = render(<WhatsAppBlocks text={'3. c\n4. d'} />);
    const ol = container.querySelector('ol');
    expect(ol).not.toBeNull();
    expect(ol!.getAttribute('start')).toBe('3');
    expect(ol!.className).toContain('list-decimal');
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['c', 'd']);
  });

  it('turns bold and italic into strong and em with no raw marker on screen', () => {
    const { container } = render(<WhatsAppBlocks text={'*Total* is _low_\n- *Alpha* here\n- _Beta_ there'} />);
    expect(container.querySelectorAll('strong').length).toBe(2);
    expect(container.querySelectorAll('em').length).toBe(2);
    expect(container.textContent).not.toContain('*');
    expect(container.textContent).not.toContain('_');
    const first = screen.getAllByRole('listitem')[0];
    expect(first.querySelector('strong')?.textContent).toBe('Alpha');
  });

  it('makes a bare URL a link, inside an item too', () => {
    render(<WhatsAppBlocks text={'See https://example.invalid/a\n- https://example.invalid/b'} />);
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(['https://example.invalid/a', 'https://example.invalid/b']);
  });

  it('keeps line breaks of a text block', () => {
    const { container } = render(<WhatsAppBlocks text={'line one\nline two'} />);
    const block = container.firstElementChild as HTMLElement;
    expect(block.textContent).toBe('line one\nline two');
    expect(`${block.className} ${block.innerHTML}`).toMatch(/whitespace-pre-(wrap|line)/);
  });

  it('keeps literal HTML in a reply as text', () => {
    const { container } = render(<WhatsAppBlocks text={'<b>not bold</b> <script>alert(1)</script>\n- <img src=x>'} />);
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('<b>not bold</b>');
    expect(container.textContent).toContain('<img src=x>');
  });

  it('renders nothing for an empty reply', () => {
    const { container } = render(<WhatsAppBlocks text="" />);
    expect(container.textContent).toBe('');
    expect(container.querySelector('ul,ol')).toBeNull();
  });
});

// AGENTIC-UNIFY PR 3, review round 1 (red): a reply of "3" must mean the row marked 3.
describe('WhatsAppBlocks: printed numbers and item lines (review round 1)', () => {
  it('gives each ordered item its printed number as li value', () => {
    render(<WhatsAppBlocks text={'1. Alice\n3. Carol'} />);
    const items = screen.getAllByRole('listitem');
    expect(items.map((li) => li.getAttribute('value'))).toEqual(['1', '3']);
  });

  it('draws a card with lines under its marker as two items, keeping the line breaks on screen', () => {
    render(<WhatsAppBlocks text={'1. *Code:* A\n*Qty:* 5\n*Loc:* X\n2. *Code:* B'} />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe('Code: A\nQty: 5\nLoc: X');
    expect(items[0].className).toMatch(/whitespace-pre-(wrap|line)/);
    expect(items[0].querySelectorAll('strong')).toHaveLength(3);
    expect(items[1].textContent).toBe('Code: B');
  });

  it('control: an unordered item carries no value attribute', () => {
    render(<WhatsAppBlocks text={'- a\n- b'} />);
    expect(screen.getAllByRole('listitem').map((li) => li.getAttribute('value'))).toEqual([null, null]);
  });
});

// Round 8: a single-backtick span is inline code on the panel, never raw backticks (AC-21).
describe('WhatsAppBlocks: inline code (round 8)', () => {
  it('draws a backtick span as a code element and keeps the text around it', () => {
    const { container } = render(<WhatsAppBlocks text={'page (`/scm/sales-orders`) here'} />);
    const codes = container.querySelectorAll('code');
    expect(codes).toHaveLength(1);
    expect(codes[0].textContent).toBe('/scm/sales-orders');
    expect(container.textContent).not.toContain('`');
    expect(container.textContent).toBe('page (/scm/sales-orders) here');
  });

  it('draws two spans inside one list item as two code elements', () => {
    render(<WhatsAppBlocks text={'- open `/a` and `/b`'} />);
    const li = screen.getAllByRole('listitem')[0];
    expect(Array.from(li.querySelectorAll('code')).map((c) => c.textContent)).toEqual(['/a', '/b']);
    expect(li.textContent).not.toContain('`');
  });

  it('keeps bold working beside inline code', () => {
    const { container } = render(<WhatsAppBlocks text={'*see* `/a`'} />);
    expect(container.querySelector('strong')?.textContent).toBe('see');
    expect(container.querySelector('code')?.textContent).toBe('/a');
    expect(container.textContent).not.toContain('`');
  });

  it('pin: a triple-backtick fence stays one code block', () => {
    const { container } = render(<WhatsAppBlocks text={'SKU ```SKU-1``` ok'} />);
    const codes = container.querySelectorAll('code');
    expect(codes).toHaveLength(1);
    expect(codes[0].textContent).toBe('SKU-1');
  });

  it('pin: a lone backtick stays as typed', () => {
    const { container } = render(<WhatsAppBlocks text={"it's 5` wide"} />);
    expect(container.textContent).toBe("it's 5` wide");
    expect(container.querySelector('code')).toBeNull();
  });

  it('keeps literal HTML inside backticks as text', () => {
    const { container } = render(<WhatsAppBlocks text={'`<b>x</b>`'} />);
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('code')?.textContent).toBe('<b>x</b>');
  });
});

// Round 9: a marker that wraps a code span must style the run, not print its raw ends (AC-21).
describe('WhatsAppBlocks: a marker around inline code (round 9)', () => {
  it('bold around a code span: strong holding a code element, no raw * or backtick', () => {
    const { container } = render(<WhatsAppBlocks text={'*Sales Orders (`/scm/sales-orders`)*'} />);
    const strong = container.querySelector('strong');
    expect(strong).not.toBeNull();
    expect(strong!.querySelector('code')?.textContent).toBe('/scm/sales-orders');
    expect(container.textContent).not.toContain('*');
    expect(container.textContent).not.toContain('`');
    expect(container.textContent).toBe('Sales Orders (/scm/sales-orders)');
  });

  it('italic around a code span: em holding a code element, no raw _ or backtick', () => {
    const { container } = render(<WhatsAppBlocks text={'_Sales Orders (`/scm/sales-orders`)_'} />);
    const em = container.querySelector('em');
    expect(em).not.toBeNull();
    expect(em!.querySelector('code')?.textContent).toBe('/scm/sales-orders');
    expect(container.textContent).not.toContain('_');
    expect(container.textContent).not.toContain('`');
  });

  it('strike around a code span: s holding a code element, no raw ~ or backtick', () => {
    const { container } = render(<WhatsAppBlocks text={'~Sales Orders (`/scm/sales-orders`)~'} />);
    const s = container.querySelector('s');
    expect(s).not.toBeNull();
    expect(s!.querySelector('code')?.textContent).toBe('/scm/sales-orders');
    expect(container.textContent).not.toContain('~');
    expect(container.textContent).not.toContain('`');
  });

  it('two code spans inside one bold, with text before and after on the same line', () => {
    const { container } = render(<WhatsAppBlocks text={'Open *`/a` or `/b`* now'} />);
    const strong = container.querySelector('strong');
    expect(strong).not.toBeNull();
    expect(Array.from(strong!.querySelectorAll('code')).map((c) => c.textContent)).toEqual(['/a', '/b']);
    expect(container.textContent).toBe('Open /a or /b now');
  });

  it('a wrapped code span inside a list item', () => {
    render(<WhatsAppBlocks text={'- *Orders (`/scm/orders`)*\n- plain'} />);
    const first = screen.getAllByRole('listitem')[0];
    expect(first.querySelector('strong code')?.textContent).toBe('/scm/orders');
    expect(first.textContent).toBe('Orders (/scm/orders)');
  });

  it('literal HTML inside a bold that wraps code stays text', () => {
    const { container } = render(<WhatsAppBlocks text={'*<b>x</b> `<i>y</i>`*'} />);
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('i')).toBeNull();
    expect(container.querySelector('code')?.textContent).toBe('<i>y</i>');
    expect(container.textContent).toBe('<b>x</b> <i>y</i>');
  });

  it('pin: bold beside code, as separate runs', () => {
    const { container } = render(<WhatsAppBlocks text={'*a* `b`'} />);
    expect(container.querySelector('strong')?.textContent).toBe('a');
    expect(container.querySelector('code')?.textContent).toBe('b');
    expect(container.textContent).toBe('a b');
  });

  it('pin: a lone * on a line with code stays as typed', () => {
    const { container } = render(<WhatsAppBlocks text={'5 * 3 is `15`'} />);
    expect(container.textContent).toBe('5 * 3 is 15');
    expect(container.querySelector('strong')).toBeNull();
    expect(container.querySelector('code')?.textContent).toBe('15');
  });

  it('pin: a lone backtick beside a bold stays as typed', () => {
    const { container } = render(<WhatsAppBlocks text={"*a* it's 5` wide"} />);
    expect(container.textContent).toBe("a it's 5` wide");
    expect(container.querySelector('code')).toBeNull();
  });
});

// Round 9, second pass: the slot that stands in for a code span (edge cases of the mask-and-fill).
describe('WhatsAppBlocks: code slots (round 9, second pass)', () => {
  const SLOT = '';

  it('keeps spans in order across segments: bold, plain, a fence, italic', () => {
    const { container } = render(<WhatsAppBlocks text={'*`/a`* and `/b` ```c``` _`/d`_'} />);
    expect(Array.from(container.querySelectorAll('code')).map((c) => c.textContent)).toEqual(['/a', '/b', 'c', '/d']);
    expect(container.textContent).not.toContain('`');
    expect(container.textContent).not.toContain('*');
    expect(container.textContent).not.toContain(SLOT);
  });

  it('a literal U+E000 in the reply never shows, and adds no extra or empty code element', () => {
    const { container } = render(<WhatsAppBlocks text={`before ${SLOT} middle \`x\` after`} />);
    expect(container.textContent).not.toContain(SLOT);
    const codes = Array.from(container.querySelectorAll('code'));
    expect(codes.map((c) => c.textContent)).toEqual(['x']);
    expect(container.textContent).toContain('before');
    expect(container.textContent).toContain('after');
  });

  it('a literal U+E000 before a bold-wrapped span leaves the span text right', () => {
    const { container } = render(<WhatsAppBlocks text={`${SLOT} *\`/a\`* ${SLOT}`} />);
    expect(container.textContent).not.toContain(SLOT);
    expect(Array.from(container.querySelectorAll('code')).map((c) => c.textContent)).toEqual(['/a']);
    expect(container.querySelector('strong code')?.textContent).toBe('/a');
  });

  it('a URL directly before a code span: any link rendered carries no U+E000 in its href', () => {
    const { container } = render(<WhatsAppBlocks text={'https://x.test/a`b`'} />);
    for (const a of Array.from(container.querySelectorAll('a'))) {
      expect(a.getAttribute('href') ?? '').not.toContain(SLOT);
      expect(decodeURIComponent(a.getAttribute('href') ?? '')).not.toContain(SLOT);
    }
    expect(container.textContent).not.toContain(SLOT);
    expect(container.querySelector('code')?.textContent).toBe('b');
  });
});

describe('WhatsAppBlocks: the agent result table (AI-TOOLS-WAVE2 crew pass, 5 Nov)', () => {
  const reply = [
    'Payout this month: RM 1,234.50.',
    '',
    'Commission payout by agent, Period 01/11/2026 to 30/11/2026',
    '',
    '| Agent | Commission payout |',
    '|---|---|',
    '| AG1 | 1,000.00 |',
    '| AG2 | 234.50 |',
    '| Total | 1,234.50 |',
    '',
    'Periods containing today (05/11/2026).',
  ].join('\n');

  it('renders the markdown table as a real table, not raw "|" text', () => {
    const { container } = render(<WhatsAppBlocks text={reply} />);
    const table = container.querySelector('table');
    expect(table).not.toBeNull();
    expect(Array.from(table!.querySelectorAll('th')).map((c) => c.textContent)).toEqual(['Agent', 'Commission payout']);
    const rows = Array.from(table!.querySelectorAll('tbody tr')).map((r) => Array.from(r.querySelectorAll('td')).map((c) => c.textContent));
    expect(rows).toEqual([['AG1', '1,000.00'], ['AG2', '234.50'], ['Total', '1,234.50']]);
    expect(container.textContent).not.toContain('|');
    expect(container.textContent).toContain('Payout this month: RM 1,234.50.');
    expect(container.textContent).toContain('Periods containing today (05/11/2026).');
  });

  it('a "|" line with no separator row stays text', () => {
    const { container } = render(<WhatsAppBlocks text={'a | b\n| just a pipe |'} />);
    expect(container.querySelector('table')).toBeNull();
    expect(container.textContent).toContain('| just a pipe |');
  });
});
