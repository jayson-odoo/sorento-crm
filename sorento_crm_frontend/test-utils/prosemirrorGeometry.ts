/**
 * jsdom has no layout, and ProseMirror scrolls the caret into view after a focus or an edit (a
 * frame later, so the error can land in whichever test is running then). Import this for its
 * side effect in a test that focuses a rich text editor: the geometry calls answer "nothing on
 * screen" instead of throwing. Same stub as `components/ui/rich-text-editor.paste.test.tsx`.
 */
const emptyRects = { length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] };
for (const proto of [Range.prototype, Text.prototype, Element.prototype] as unknown as Array<
  Record<string, unknown>
>) {
  if (typeof proto.getClientRects !== 'function') proto.getClientRects = () => emptyRects;
}
if (typeof Range.prototype.getBoundingClientRect !== 'function') {
  Range.prototype.getBoundingClientRect = () => new DOMRect(0, 0, 0, 0);
}

export {};
