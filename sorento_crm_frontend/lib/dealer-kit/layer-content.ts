/**
 * What a text layer stores after an edit in the Inspector's rich Content box (DESIGNER-RICH-TEXT).
 *
 * Content with no inline formatting is stored as plain text, one line per paragraph: the format
 * every template used before, so a template opened and edited without formatting keeps it. Only
 * content that carries a mark (bold, italic, underline, strike, a colour, an alignment) is stored
 * as the editor's HTML, which `rich-text.ts` parses for canvas, preview and print alike.
 */

import { isRich } from './rich-text';

/** Elements that carry no formatting of their own. A bare `<span>` is what an editor leaves
 * behind once a colour is removed. */
function isUnformatted(el: Element): boolean {
  const tag = el.tagName.toLowerCase();
  if (tag === 'br') return true;
  if (tag !== 'span' || el.attributes.length > 0) return false;
  return Array.from(el.children).every(isUnformatted);
}

/** The editor's HTML (`<p>` per line) as the value the layer stores. */
export function contentFromEditorHtml(html: string): string {
  if (!html || html === '<p></p>') return '';
  if (typeof DOMParser === 'undefined') return html;
  const body = new DOMParser().parseFromString(html, 'text/html').body;
  const blocks = Array.from(body.childNodes);
  const plain = blocks.every(
    (node) =>
      node.nodeType === 1 &&
      (node as Element).tagName.toLowerCase() === 'p' &&
      (node as Element).attributes.length === 0 &&
      Array.from((node as Element).children).every(isUnformatted),
  );
  if (!plain) return html;
  const text = blocks
    .map((node) => {
      const p = node as Element;
      p.querySelectorAll('br').forEach((br) => br.replaceWith('\n'));
      return p.textContent ?? '';
    })
    .join('\n');
  // Plain text that would READ as rich (somebody typed "<p>") stays HTML, or it would be parsed as
  // markup the next time it is drawn.
  return isRich(text) ? html : text;
}
