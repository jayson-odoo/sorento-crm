/**
 * WhatsApp message text, parsed into styled segments.
 *
 * Every message in the Conversations inbox was composed for WhatsApp, so it
 * arrives in WhatsApp's own markup: `*bold*`, `_italic_`, `~strike~` and
 * ```monospace``` blocks, with bare URLs the handset turns into links. Rendered
 * as plain text those markers read as punctuation - a stock-availability reply
 * shows a literal `*Product Code:*` and its portal link is not clickable.
 *
 * This module is the parse half only: it returns flat segments carrying style
 * flags, and the React rendering lives with the chat list. Flat-with-flags
 * rather than a tree because the marks compose (`*_both_*`) but never need to
 * nest structurally, and a flat list stays trivial to intersect with the search
 * highlighter afterwards.
 */

export interface WhatsAppTextSegment {
  text: string;
  bold?: boolean;
  italic?: boolean;
  strike?: boolean;
  /** Rendered in a monospace block: WhatsApp's triple-backtick fence. */
  code?: boolean;
  /** Absolute href when this segment is a link. */
  href?: string;
}

type Marks = Pick<WhatsAppTextSegment, 'bold' | 'italic' | 'strike'>;

/**
 * One formatting pair, with WhatsApp's own boundary rules.
 *
 * A marker only opens at the start of a word and only closes at the end of one:
 * the run it opens must begin and end with a non-space, the opener must follow
 * whitespace or an opening bracket, and the closer must be followed by
 * whitespace or sentence punctuation. Those conditions are what stop a promotion
 * name like `PROMO_07052026 DEALER ... UPDATED_2026` (two underscores mid-word,
 * both real in this data) from italicising everything between them. The lazy
 * inner group takes the NEAREST valid closer, matching the handset.
 */
const INLINE_PATTERN = /(^|[\s([{<"'])([*_~])(?=\S)([\s\S]*?\S)\2(?=$|[\s)\]}>"'.,!?:;])/;

const MARK_BY_CHAR: Record<string, keyof Marks> = {
  '*': 'bold',
  _: 'italic',
  '~': 'strike',
};

/** Triple-backtick fence. Everything inside is literal - no marks, no links. */
const CODE_FENCE = /```([\s\S]*?)```/;

/**
 * Bare URLs, as WhatsApp linkifies them: an explicit scheme, or a `www.` host.
 *
 * Trailing sentence punctuation is deliberately excluded from the match so
 * "see https://x.test/a." links `https://x.test/a` and leaves the full stop as
 * text. Closing brackets are excluded for the same reason, which costs us a
 * link that genuinely ends in one - rare next to the sentence case.
 */
const URL_PATTERN = /\b(?:https?:\/\/|www\.)[^\s<>]*[^\s<>.,;:!?)\]}'"]/gi;

function withMark(marks: Marks, char: string): Marks {
  const key = MARK_BY_CHAR[char];
  return key ? { ...marks, [key]: true } : marks;
}

/** Split a plain run into text and link segments. */
function linkify(text: string, marks: Marks): WhatsAppTextSegment[] {
  if (!text) return [];
  const out: WhatsAppTextSegment[] = [];
  let cursor = 0;
  URL_PATTERN.lastIndex = 0;
  for (const found of text.matchAll(URL_PATTERN)) {
    const start = found.index ?? 0;
    const raw = found[0];
    if (start > cursor) out.push({ text: text.slice(cursor, start), ...marks });
    out.push({
      text: raw,
      href: /^https?:\/\//i.test(raw) ? raw : `https://${raw}`,
      ...marks,
    });
    cursor = start + raw.length;
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor), ...marks });
  return out;
}

/** Recursively resolve inline marks, then linkify whatever is left plain. */
function parseInline(text: string, marks: Marks): WhatsAppTextSegment[] {
  if (!text) return [];
  const found = INLINE_PATTERN.exec(text);
  if (!found) return linkify(text, marks);

  const [whole, prefix, marker, inner] = found;
  // The prefix is the boundary character the pattern had to look at; it belongs
  // to the text BEFORE the marker, not to the styled run.
  const start = found.index + prefix.length;
  const end = found.index + whole.length;
  return [
    ...parseInline(text.slice(0, start), marks),
    ...parseInline(inner, withMark(marks, marker)),
    ...parseInline(text.slice(end), marks),
  ];
}

/**
 * `text` as styled segments. Always returns at least one segment for non-empty
 * input, so a caller can render the result unconditionally.
 */
export function parseWhatsAppText(text: string): WhatsAppTextSegment[] {
  if (!text) return [];
  const out: WhatsAppTextSegment[] = [];
  let rest = text;
  for (;;) {
    const fence = CODE_FENCE.exec(rest);
    if (!fence) break;
    const start = fence.index;
    out.push(...parseInline(rest.slice(0, start), {}));
    const body = fence[1];
    if (body) out.push({ text: body, code: true });
    rest = rest.slice(start + fence[0].length);
  }
  out.push(...parseInline(rest, {}));
  return out.filter((segment) => segment.text.length > 0);
}

/**
 * `text` with its WhatsApp markers removed and nothing else changed.
 *
 * For the places that need the WORDS but cannot carry the styling: a one-line
 * inbox preview, and the quoted-reply excerpt (which sits inside a button, so a
 * rendered link there would be invalid HTML). Same parser as the full renderer,
 * so the two can never disagree about what is a marker.
 */
export function stripWhatsAppMarkup(text: string): string {
  if (!text) return '';
  return parseWhatsAppText(text)
    .map((segment) => segment.text)
    .join('');
}
