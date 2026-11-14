/**
 * SPARE-PART-ORDER-REQUEST owner rename (13 Nov), red-first (Phase 2). F4 source guard.
 * No non-test .ts/.tsx under app, components, config, lib carries the words "spare part
 * request" in a string literal or JSX text. Comments are ignored; identifiers
 * (SparePartRequestForm), routes (/spare-part-requests), permission slugs and the
 * `spare_part_request` key do not match the spaced phrase.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = process.cwd();
const DIRS = ['app', 'components', 'config', 'lib'];
const SKIP_DIR = new Set(['node_modules', '.next', '__mocks__']);

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      if (!SKIP_DIR.has(name)) walk(full, out);
    } else if (
      /\.(ts|tsx)$/.test(name) &&
      !/\.d\.ts$/.test(name) &&
      !/\.(test|spec)\.(ts|tsx)$/.test(name)
    ) {
      out.push(full);
    }
  }
  return out;
}

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:'"`\\])\/\/.*$/gm, '$1');
}

describe('F4: no "spare part request" wording left in user-visible text', () => {
  it('finds none in non-test source outside comments', () => {
    const hits: string[] = [];
    for (const dir of DIRS) {
      for (const file of walk(path.join(ROOT, dir))) {
        const lines = stripComments(readFileSync(file, 'utf8')).split('\n');
        lines.forEach((line, i) => {
          if (/spare\s+part\s+request/i.test(line)) {
            hits.push(`${path.relative(ROOT, file)}:${i + 1}: ${line.trim().slice(0, 100)}`);
          }
        });
      }
    }
    expect(hits, `${hits.length} hits:\n${hits.join('\n')}`).toEqual([]);
  });
});
