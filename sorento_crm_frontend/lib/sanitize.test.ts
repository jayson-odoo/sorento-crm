/**
 * E-2 — sanitizeHtml must strip XSS vectors from untrusted HTML while keeping
 * ordinary formatting, before it reaches dangerouslySetInnerHTML.
 */
import { describe, it, expect } from 'vitest';

import { sanitizeHtml, sanitizedHtml } from './sanitize';

describe('sanitizeHtml', () => {
  it('strips <script> tags', () => {
    const out = sanitizeHtml('<p>hi</p><script>alert(1)</script>');
    expect(out).toContain('<p>hi</p>');
    expect(out.toLowerCase()).not.toContain('<script');
  });

  it('strips inline event handlers', () => {
    const out = sanitizeHtml('<img src=x onerror="alert(1)">');
    expect(out.toLowerCase()).not.toContain('onerror');
  });

  it('drops javascript: URLs', () => {
    const out = sanitizeHtml('<a href="javascript:alert(1)">x</a>');
    expect(out.toLowerCase()).not.toContain('javascript:');
  });

  it('keeps ordinary formatting and links', () => {
    const out = sanitizeHtml('<b>bold</b> <a href="https://x.test">link</a>');
    expect(out).toContain('<b>bold</b>');
    expect(out).toContain('href="https://x.test"');
  });

  it('handles null/undefined/empty', () => {
    expect(sanitizeHtml(null)).toBe('');
    expect(sanitizeHtml(undefined)).toBe('');
    expect(sanitizeHtml('')).toBe('');
  });

  it('sanitizedHtml returns a __html object', () => {
    expect(sanitizedHtml('<b>x</b>')).toEqual({ __html: '<b>x</b>' });
  });
});
