/**
 * The portal home's New button and cards link into the slug tree
 * (`/portal/c/{slug}/sales_opportunity/...`, `portalNewPath` / `portalDetailPath`), so both
 * pages must exist there, like Price Tag Request's (browser pass of fix round 2: New 404'd).
 */
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const SLUG_TREE = join(__dirname, '..', 'c', '[slug]', 'sales_opportunity');

describe('sales opportunity pages in the portal slug tree', () => {
  it.each([['new', 'page.tsx'], ['[id]', 'page.tsx']])('%s/%s exists', (dir, file) => {
    expect(existsSync(join(SLUG_TREE, dir, file))).toBe(true);
  });
});
