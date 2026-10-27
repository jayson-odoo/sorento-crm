/**
 * FR-18 (CATALOG-IMAGES): Next 15.5's rewrite proxy forwards a request body only up to 10 MB
 * unless experimental.middlewareClientMaxBodySize says otherwise, so a 16.6 MB catalogue never
 * reached the backend. The ceiling must cover the 50 MB upload limit.
 */
import { describe, it, expect } from 'vitest';
// @ts-expect-error plain ESM config, no types
import nextConfig from '../next.config.mjs';

function toBytes(value: unknown): number {
  if (typeof value === 'number') return value;
  const match = /^\s*(\d+(?:\.\d+)?)\s*(b|kb|mb|gb)?\s*$/i.exec(String(value ?? ''));
  if (!match) return 0;
  const unit = (match[2] ?? 'b').toLowerCase();
  const factor = { b: 1, kb: 1024, mb: 1024 ** 2, gb: 1024 ** 3 }[unit] as number;
  return Number(match[1]) * factor;
}

describe('next.config body limit', () => {
  it('lets the rewrite proxy forward at least 55 MB of request body', async () => {
    const config = typeof nextConfig === 'function' ? await nextConfig('phase-production-build', {}) : nextConfig;
    const limit = config.experimental?.middlewareClientMaxBodySize;
    expect(limit, 'experimental.middlewareClientMaxBodySize is not set').toBeDefined();
    expect(toBytes(limit)).toBeGreaterThanOrEqual(55 * 1024 * 1024);
  });
});
