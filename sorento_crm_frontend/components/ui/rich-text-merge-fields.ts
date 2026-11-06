/**
 * `{{path}}` merge-field tokens inside the shared rich text editor (DESIGNER-RICH-TEXT).
 *
 * A token is ONE inline atom node: a mark (bold, a colour) covers it whole and a selection can
 * never split it. The atom exists only inside the editor. What goes in and comes out is plain
 * `{{path}}` text inside the HTML, so the stored value is the same shape every reader
 * (`lib/dealer-kit/rich-text.ts`, the merge-field resolver) already understands.
 */
import { mergeAttributes, Node } from '@tiptap/react';
import type { NodeType } from '@tiptap/pm/model';
import { Plugin, PluginKey } from '@tiptap/pm/state';

const TOKEN = /\{\{\s*([^{}]+?)\s*\}\}/g;
const ATTR = 'data-merge-field';

/** The editor's HTML with every token wrapped in its merge-field span (idempotent). */
export function wrapMergeFieldTokens(html: string): string {
  if (!html.includes('{{') || typeof DOMParser === 'undefined') return html;
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  const texts: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!(node.parentElement?.hasAttribute(ATTR) ?? false)) texts.push(node as Text);
  }
  let changed = false;
  for (const text of texts) {
    const value = text.data;
    // `{{ }}` names no field: it stays text.
    const matches = [...value.matchAll(TOKEN)].filter((match) => match[1].trim() !== '');
    if (matches.length === 0) continue;
    changed = true;
    const fragment = doc.createDocumentFragment();
    let at = 0;
    for (const match of matches) {
      const start = match.index ?? 0;
      if (start > at) fragment.append(value.slice(at, start));
      const span = doc.createElement('span');
      span.setAttribute(ATTR, match[1].trim());
      span.textContent = match[0];
      fragment.append(span);
      at = start + match[0].length;
    }
    if (at < value.length) fragment.append(value.slice(at));
    text.replaceWith(fragment);
  }
  return changed ? doc.body.innerHTML : html;
}

/** Every merge-field span back to its plain `{{path}}` text, marks around it kept. */
export function unwrapMergeFieldTokens(html: string): string {
  if (!html.includes(ATTR) || typeof DOMParser === 'undefined') return html;
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.body.querySelectorAll(`span[${ATTR}]`).forEach((span) => {
    span.replaceWith(`{{${span.getAttribute(ATTR) ?? ''}}}`);
  });
  return doc.body.innerHTML;
}

/** Turns any complete `{{path}}` that lands in a text node (typed, pasted, inserted) into an
 * atom, keeping the marks the text had. */
function tokenizePlugin(type: NodeType) {
  return new Plugin({
    key: new PluginKey('mergeFieldTokens'),
    appendTransaction(transactions, _old, state) {
      if (!transactions.some((tr) => tr.docChanged)) return null;
      const found: Array<{ from: number; to: number; path: string; marks: readonly unknown[] }> = [];
      state.doc.descendants((node, pos) => {
        if (!node.isText || !node.text?.includes('{{')) return;
        for (const match of node.text.matchAll(TOKEN)) {
          if (match[1].trim() === '') continue;
          const from = pos + (match.index ?? 0);
          found.push({ from, to: from + match[0].length, path: match[1].trim(), marks: node.marks });
        }
      });
      if (found.length === 0) return null;
      const tr = state.tr;
      for (const hit of found.reverse()) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        tr.replaceWith(hit.from, hit.to, type.create({ path: hit.path }, null, hit.marks as any));
      }
      return tr;
    },
  });
}

export const MergeFieldNode = Node.create({
  name: 'mergeField',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      path: {
        default: '',
        parseHTML: (element) => element.getAttribute(ATTR) ?? '',
        renderHTML: (attributes) => ({ [ATTR]: attributes.path }),
      },
    };
  },

  parseHTML() {
    return [{ tag: `span[${ATTR}]` }];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(HTMLAttributes, {
        class: 'rounded bg-sky-50 px-0.5 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300',
      }),
      `{{${node.attrs.path}}}`,
    ];
  },

  renderText({ node }) {
    return `{{${node.attrs.path}}}`;
  },

  addProseMirrorPlugins() {
    return [tokenizePlugin(this.type)];
  },
});
