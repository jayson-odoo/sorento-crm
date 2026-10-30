import { describe, expect, it } from 'vitest';
import { waMeUrl } from './wa-me';

describe('waMeUrl', () => {
  it('builds the click-to-chat URL from digits and an encoded text', () => {
    expect(waMeUrl('60120000001', 'Hello')).toBe('https://wa.me/60120000001?text=Hello');
  });

  it('keeps only digits of the phone', () => {
    expect(waMeUrl('+60 12-000 0001', 'x')).toBe('https://wa.me/60120000001?text=x');
  });

  it('encodes spaces, newlines, ampersand, hash and plus in the text', () => {
    const url = waMeUrl('60120000001', 'a b\nc&d#e+f');
    expect(url).toBe('https://wa.me/60120000001?text=a%20b%0Ac%26d%23e%2Bf');
  });

  it('gives the number-less form when there are no digits', () => {
    expect(waMeUrl('', 'Hi there')).toBe('https://wa.me/?text=Hi%20there');
    expect(waMeUrl('abc', 'Hi')).toBe('https://wa.me/?text=Hi');
  });
});
