/**
 * Text split into plain runs and clickable URLs.
 *
 * Message bubbles get their links from `parseWhatsAppText`, which linkifies as
 * part of parsing the handset markup. An internal note does not go through that
 * parser (it is typed in the CRM, not on a handset), so a pasted Respond.io
 * deep link used to sit in the note as dead text. This module is the link half
 * on its own, and the WhatsApp parser now calls it too, so the two readers can
 * never disagree about what counts as a URL.
 */

export interface LinkSegment {
  text: string;
  /** Absolute href when this segment is a link. */
  href?: string;
}

/**
 * Bare URLs, as WhatsApp linkifies them: an explicit scheme, or a `www.` host.
 *
 * Trailing sentence punctuation is deliberately excluded from the match so
 * "see https://x.test/a." links `https://x.test/a` and leaves the full stop as
 * text. Closing brackets are excluded for the same reason, which costs us a
 * link that genuinely ends in one - rare next to the sentence case. A `#`
 * fragment is part of the path and is kept.
 *
 * Only `http`/`https`/`www.` can ever match, so no other scheme (`javascript:`
 * above all) can reach an `href`.
 */
const URL_PATTERN = /\b(?:https?:\/\/|www\.)[^\s<>]*[^\s<>.,;:!?)\]}'"]/gi;

/**
 * `text` as alternating plain and link segments. Returns an empty list for
 * empty input, so a caller can render the result unconditionally.
 */
export function linkifySegments(text: string): LinkSegment[] {
  if (!text) return [];
  const out: LinkSegment[] = [];
  let cursor = 0;
  URL_PATTERN.lastIndex = 0;
  for (const found of text.matchAll(URL_PATTERN)) {
    const start = found.index ?? 0;
    const raw = found[0];
    if (start > cursor) out.push({ text: text.slice(cursor, start) });
    out.push({ text: raw, href: /^https?:\/\//i.test(raw) ? raw : `https://${raw}` });
    cursor = start + raw.length;
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor) });
  return out;
}
