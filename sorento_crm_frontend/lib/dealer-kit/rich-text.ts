/**
 * The one parser for a rich price tag description (PRICETAG-COMBO-FORMAT S3).
 *
 * The stored value is either legacy plain text or the sanitised HTML the shared editor emits
 * (`app/utils/tag_rich_text.py` is the server allow-list). The canvas, the request preview and the
 * print page all draw the blocks of runs this returns, so none of them ever touches HTML: the
 * string is parsed with `DOMParser` (which runs no script and loads nothing) and walked, never
 * written into an element with `innerHTML`.
 *
 * Plain text is one paragraph per line. Colours are re-validated here (hex / rgb only): a run with
 * an invalid colour draws in the layer colour.
 */

export type RichRun = {
  text: string;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  strike?: boolean;
  code?: boolean;
  color?: string | null;
  highlight?: string | null;
};

export type RichAlign = 'left' | 'center' | 'right';

export type RichBlock = {
  kind: 'p' | 'h1' | 'h2' | 'h3' | 'li' | 'quote';
  runs: RichRun[];
  align?: RichAlign | null;
  marker?: string | null;
  level?: number;
  sizeFactor: number;
  bold?: boolean;
};

/** A value is rich iff it starts with an allowed block tag (same rule as the server). */
const RICH_START = /^\s*<(?:p|h1|h2|h3|ul|ol|blockquote)(?=[\s>])/i;

export function isRich(value: string | null | undefined): boolean {
  return !!value && RICH_START.test(value);
}

const COLOUR =
  /^(?:#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\))$/;

const HEADING_FACTOR: Record<string, number> = { h1: 1.4, h2: 1.2, h3: 1.1 };

type Marks = Omit<RichRun, 'text'>;

/** The declarations of an inline `style` attribute, read from the raw string (the DOM's own
 * `style` object rewrites colours to `rgb()` and would lose what was stored). */
function declarations(el: Element): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of (el.getAttribute('style') ?? '').split(';')) {
    const at = part.indexOf(':');
    if (at < 0) continue;
    out[part.slice(0, at).trim().toLowerCase()] = part.slice(at + 1).trim();
  }
  return out;
}

export function validColour(value: string | undefined): string | null {
  return value && COLOUR.test(value) ? value : null;
}

function alignOf(el: Element): RichAlign | null {
  const value = declarations(el)['text-align']?.toLowerCase();
  return value === 'left' || value === 'center' || value === 'right' ? value : null;
}

function marksFor(el: Element, inherited: Marks): Marks {
  const tag = el.tagName.toLowerCase();
  const marks: Marks = { ...inherited };
  if (tag === 'strong' || tag === 'b') marks.bold = true;
  else if (tag === 'em' || tag === 'i') marks.italic = true;
  else if (tag === 'u') marks.underline = true;
  else if (tag === 's' || tag === 'strike' || tag === 'del') marks.strike = true;
  else if (tag === 'code') marks.code = true;
  if (tag === 'span' || tag === 'mark') {
    const css = declarations(el);
    const color = validColour(css.color);
    const background = validColour(css['background-color']);
    if (color) marks.color = color;
    if (background) marks.highlight = background;
  }
  return marks;
}

function sameMarks(a: RichRun, b: RichRun): boolean {
  return (
    !!a.bold === !!b.bold &&
    !!a.italic === !!b.italic &&
    !!a.underline === !!b.underline &&
    !!a.strike === !!b.strike &&
    !!a.code === !!b.code &&
    (a.color ?? null) === (b.color ?? null) &&
    (a.highlight ?? null) === (b.highlight ?? null)
  );
}

function pushRun(runs: RichRun[], text: string, marks: Marks) {
  if (!text) return;
  const run: RichRun = { text, ...marks };
  const last = runs[runs.length - 1];
  if (last && sameMarks(last, run)) last.text += text;
  else runs.push(run);
}

/** The runs inside an inline context; block children (nested lists) are skipped here. */
function collectRuns(node: Node, marks: Marks, runs: RichRun[]) {
  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === 3) {
      pushRun(runs, (child.textContent ?? '').replace(/\r?\n/g, ' '), marks);
    } else if (child.nodeType === 1) {
      const el = child as Element;
      const tag = el.tagName.toLowerCase();
      if (tag === 'br') pushRun(runs, '\n', marks);
      else if (tag === 'script' || tag === 'style') continue;
      else if (tag === 'ul' || tag === 'ol') continue;
      else collectRuns(el, marksFor(el, marks), runs);
    }
  }
}

function block(kind: RichBlock['kind'], runs: RichRun[], extra: Partial<RichBlock> = {}): RichBlock {
  const heading = HEADING_FACTOR[kind];
  return {
    kind,
    runs,
    align: null,
    sizeFactor: heading ?? 1,
    ...(heading ? { bold: true } : {}),
    ...extra,
  };
}

function firstParagraph(item: Element): Element | null {
  return Array.from(item.children).find((child) => child.tagName.toLowerCase() === 'p') ?? null;
}

function listBlocks(list: Element, level: number, out: RichBlock[]) {
  const ordered = list.tagName.toLowerCase() === 'ol';
  let count = 0;
  for (const item of Array.from(list.children)) {
    if (item.tagName.toLowerCase() !== 'li') continue;
    count += 1;
    const runs: RichRun[] = [];
    collectRuns(item, {}, runs);
    out.push(
      block('li', runs, {
        marker: ordered ? `${count}.` : '•',
        level,
        align: alignOf(item) ?? alignOf(firstParagraph(item) ?? item),
      }),
    );
    for (const nested of Array.from(item.children)) {
      const tag = nested.tagName.toLowerCase();
      if (tag === 'ul' || tag === 'ol') listBlocks(nested, level + 1, out);
    }
  }
}

function walkBlocks(parent: Node, out: RichBlock[]) {
  let loose: RichRun[] = [];
  const flushLoose = () => {
    if (loose.some((run) => run.text.trim() !== '')) out.push(block('p', loose));
    loose = [];
  };
  for (const child of Array.from(parent.childNodes)) {
    if (child.nodeType === 3) {
      pushRun(loose, (child.textContent ?? '').replace(/\r?\n/g, ' '), {});
      continue;
    }
    if (child.nodeType !== 1) continue;
    const el = child as Element;
    const tag = el.tagName.toLowerCase();
    if (tag === 'script' || tag === 'style') continue;
    if (tag === 'p' || tag === 'h1' || tag === 'h2' || tag === 'h3') {
      flushLoose();
      const runs: RichRun[] = [];
      collectRuns(el, {}, runs);
      out.push(block(tag, runs, { align: alignOf(el) }));
    } else if (tag === 'ul' || tag === 'ol') {
      flushLoose();
      listBlocks(el, 1, out);
    } else if (tag === 'blockquote') {
      flushLoose();
      const inner: RichBlock[] = [];
      walkBlocks(el, inner);
      for (const entry of inner) out.push({ ...entry, kind: 'quote' });
    } else if (tag === 'div' || tag === 'section' || tag === 'article' || tag === 'table') {
      flushLoose();
      walkBlocks(el, out);
    } else {
      // Inline leftovers (a link, an unknown tag): their text, in the surrounding paragraph.
      collectRuns(el, marksFor(el, {}), loose);
    }
  }
  flushLoose();
}

/** Legacy plain text, one line per paragraph. A leftover tag in it (old data) is dropped, its text
 * kept, the same as the server's plain-text mode; text with no `<` is returned as typed. */
function plainLines(value: string): string[] {
  if (!value.includes('<')) return value.split('\n');
  const doc = new DOMParser().parseFromString(value, 'text/html');
  doc.querySelectorAll('script, style, iframe, object, embed').forEach((el) => el.remove());
  return (doc.body.textContent ?? '').split('\n');
}

export function parseRichText(value: string | null | undefined): RichBlock[] {
  if (!value) return [];
  if (!isRich(value)) {
    return plainLines(value).map((line) => block('p', line ? [{ text: line }] : []));
  }
  const doc = new DOMParser().parseFromString(value, 'text/html');
  const out: RichBlock[] = [];
  walkBlocks(doc.body, out);
  return out;
}

/** The text of a run list. */
export function runsText(runs: RichRun[]): string {
  return runs.map((run) => run.text).join('');
}

/** Blocks as plain lines: one line per block, "• " / "1. " per item, no markup. */
export function blocksPlainText(blocks: RichBlock[]): string {
  return blocks
    .map((entry) => {
      const text = runsText(entry.runs);
      if (entry.kind !== 'li') return text;
      return `${'  '.repeat((entry.level ?? 1) - 1)}${entry.marker ?? '•'} ${text}`;
    })
    .join('\n');
}

/** Same rules as the server's `plain_text`: lines per block, "• " / "1. " per item, no markup. */
export function richPlainText(value: string | null | undefined): string {
  if (!value) return '';
  if (!isRich(value)) return value;
  return blocksPlainText(parseRichText(value));
}

/** A colour safe to put in a `style` value: a hex or rgb() colour, else `fallback`. */
export function safeColour(value: string | null | undefined, fallback = 'transparent'): string {
  if (typeof value === 'string' && value.trim().toLowerCase() === 'transparent') return 'transparent';
  return validColour(value ?? undefined) ?? fallback;
}

/**
 * A value as ONE line of plain text for a place that cannot draw runs (a legacy card line, a list
 * row): paragraphs joined by a space, no markup. Plain text is returned as typed.
 */
export function richOneLine(value: string | null | undefined): string {
  if (!value) return '';
  if (!isRich(value)) return value;
  return parseRichText(value)
    .map((block) => runsText(block.runs).trim())
    .filter(Boolean)
    .join(' ');
}

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };

/**
 * What the editor is handed for a stored value: rich HTML as is; legacy plain text as one
 * paragraph per line (an editor reads plain text as a single run and would fold the lines).
 */
export function toEditorHtml(value: string | null | undefined): string {
  if (!value) return '';
  if (isRich(value)) return value;
  return value
    .split('\n')
    .map((line) => `<p>${line.replace(/[&<>"]/g, (ch) => ESCAPES[ch])}</p>`)
    .join('');
}
