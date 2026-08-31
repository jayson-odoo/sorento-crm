import { describe, expect, it } from 'vitest';
import { lineFamily } from './line-family';

const product = { line_type: 'product' as const };

describe('lineFamily', () => {
  it.each([
    ['SRTKS2435', 'sink_combo'],
    ['SRTKS2409', 'sink_combo'],
    ['SRTWB8001', 'art_basin'],
    ['SRTGB2550', 'art_basin'],
    ['SRTLMCB902-BL', 'mirror_cabinet'],
    ['SRTMCB6088-BL', 'mirror_cabinet'],
    ['SRTMRL705', 'mirror'],
    ['SRTWT7633', 'shower'],
    ['SRTWT9616-BL', 'shower'],
    ['SRTWC8036-SH-UF', 'wc'],
    ['SRTSP224', 'wc'],
    ['SRTUB6503', 'urinal'],
    ['SRTBF11833', 'furniture_set'],
  ])('%s -> %s', (code, family) => {
    expect(lineFamily(product, code)).toBe(family);
  });

  it('a set line is a furniture set whatever its code', () => {
    expect(lineFamily({ line_type: 'product_set' }, 'SRTWC8608-RL')).toBe('furniture_set');
  });

  it('an unknown or missing code falls back to ala carte', () => {
    expect(lineFamily(product, 'MOCHA-123')).toBe('ala_carte');
    expect(lineFamily(product, undefined)).toBe('ala_carte');
  });

  it('the SH inside a WC code never reads as a shower', () => {
    expect(lineFamily(product, 'SRTWC8036-SH-250')).toBe('wc');
  });
});
