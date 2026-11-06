/**
 * DESIGNER-RICH-TEXT: what a text layer stores after an edit in the Inspector's rich Content box.
 *
 * Back-compatible storage: content with no inline formatting is stored as today's plain text (one
 * line per paragraph), so an existing template that is opened and edited without formatting keeps
 * exactly the format it had. Only content that carries a mark is stored as rich HTML.
 *
 * Written test-FIRST: `layer-content.ts` does not exist yet.
 */
import { describe, expect, it } from 'vitest';

import { contentFromEditorHtml } from './layer-content';
import { isRich, toEditorHtml } from './rich-text';

describe('contentFromEditorHtml', () => {
  it('unformatted paragraphs are stored as plain lines', () => {
    expect(contentFromEditorHtml('<p>A</p><p>B</p>')).toBe('A\nB');
  });

  it('the owner example, unformatted, stays exactly the plain text it was', () => {
    const plain = '{{product.code}}\n{{product.price_tag_description}}\nLP: {{product.list_price}}';
    expect(contentFromEditorHtml(toEditorHtml(plain))).toBe(plain);
  });

  it('round-trips plain text with empty lines and characters HTML escapes', () => {
    const plain = 'a & b\n\n<c> "q" \'s\'\n  indented';
    expect(contentFromEditorHtml(toEditorHtml(plain))).toBe(plain);
  });

  it('a hard break inside a paragraph is a new line', () => {
    expect(contentFromEditorHtml('<p>a<br>b</p>')).toBe('a\nb');
  });

  it('empty editor content is the empty string', () => {
    expect(contentFromEditorHtml('')).toBe('');
    expect(contentFromEditorHtml('<p></p>')).toBe('');
  });

  it('a bold token keeps the rich HTML', () => {
    const html = '<p><strong>{{product.code}}</strong></p><p>LP: {{product.list_price}}</p>';
    const stored = contentFromEditorHtml(html);
    expect(stored).toBe(html);
    expect(isRich(stored)).toBe(true);
  });

  it.each([
    ['italic', '<p><em>x</em></p>'],
    ['underline', '<p><u>x</u></p>'],
    ['strike', '<p><s>x</s></p>'],
    ['colour', '<p><span style="color: #ff0000">x</span></p>'],
  ])('%s keeps the rich HTML', (_name, html) => {
    expect(contentFromEditorHtml(html)).toBe(html);
  });

  it('a bare span with no style is not formatting', () => {
    expect(contentFromEditorHtml('<p><span>x</span></p>')).toBe('x');
  });

  it('plain text that would READ as rich (typed "<p>") stays HTML so it is never misread', () => {
    const html = '<p>&lt;p&gt;hello</p>';
    const stored = contentFromEditorHtml(html);
    expect(stored).toBe(html);
  });
});
