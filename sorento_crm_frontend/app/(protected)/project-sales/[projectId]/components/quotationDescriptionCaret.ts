/**
 * One-step editing of a quotation line description (owner hand test, 10 Nov): the click that opens
 * the editor also places its caret, at the character that was clicked in the cell.
 *
 * The cell draws the text one way (RichDescription) and the editor another, so a point is carried
 * across as a TEXT OFFSET: the number of typed characters before it. List markers and line breaks
 * are not typed characters in the editor's document, so they are not counted on either side.
 */
import type { Node as PMNode } from '@tiptap/pm/model';
import { Selection } from '@tiptap/pm/state';

/** Characters of text before (`node`, `offset`) inside `root`, list markers and line breaks left out. */
export function textOffsetAt(root: Element, node: Node, offset: number): number {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let count = 0;
  for (let current = walker.nextNode(); current; current = walker.nextNode()) {
    const inMarker = current.parentElement?.closest('[data-rt-marker]');
    const text = current.textContent ?? '';
    if (current === node) {
      return inMarker ? count : count + text.slice(0, offset).replace(/\n/g, '').length;
    }
    if (!inMarker) count += text.replace(/\n/g, '').length;
  }
  return count;
}

/** The text offset of a viewport point inside `root`, or null when the browser cannot say. */
export function textOffsetAtPoint(root: Element, x: number, y: number): number | null {
  const doc = document as Document & {
    caretPositionFromPoint?: (x: number, y: number) => { offsetNode: Node; offset: number } | null;
    caretRangeFromPoint?: (x: number, y: number) => Range | null;
  };
  let node: Node | null = null;
  let offset = 0;
  if (typeof doc.caretPositionFromPoint === 'function') {
    const position = doc.caretPositionFromPoint(x, y);
    if (position) {
      node = position.offsetNode;
      offset = position.offset;
    }
  } else if (typeof doc.caretRangeFromPoint === 'function') {
    const range = doc.caretRangeFromPoint(x, y);
    if (range) {
      node = range.startContainer;
      offset = range.startOffset;
    }
  }
  if (!node || !root.contains(node) || node.nodeType !== Node.TEXT_NODE) return null;
  return textOffsetAt(root, node, offset);
}

/** The editor position after `count` characters of text; the end of the text when past it. */
export function docPosAtTextOffset(doc: PMNode, count: number): number {
  let remaining = count;
  let found: number | null = null;
  doc.descendants((child, pos) => {
    if (found !== null) return false;
    if (!child.isText) return true;
    const length = child.text?.length ?? 0;
    if (remaining <= length) {
      found = pos + remaining;
      return false;
    }
    remaining -= length;
    return false;
  });
  return found ?? Selection.atEnd(doc).from;
}
