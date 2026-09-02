/**
 * M1-06 - the 16 motion components nothing in the app imported.
 *
 * Written test-first: this asserted zero importers BEFORE the 16 files below
 * were deleted (confirming the deletion was safe), and now asserts the files
 * stay gone - a future PR resurrecting `components/ui/marquee.tsx` (or an
 * import of it) should fail here rather than survive to `npm run build`.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const root = path.resolve(__dirname, '../..');

const DELETED_MOTION_COMPONENTS = [
  'marquee',
  'text-reveal',
  'shimmering-text',
  'sliding-number',
  'counting-number',
  'gradient-background',
  'hover-background',
  'grid-background',
  'stepper',
  'word-rotate',
  'typing-text',
  'avatar-group',
  'video-text',
  'github-button',
  'skeleton-with-pattern',
  'svg-text',
];

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
      const rel = path.posix.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(rel);
      } else if (/\.tsx?$/.test(entry.name) && !entry.name.includes('.test.')) {
        out.push(rel);
      }
    }
  };
  walk('app');
  walk('components');
  walk('lib');
  walk('hooks');
  walk('config');
  return out;
}

describe('M1-06 the 16 unused motion components stay deleted (audit baseline: 0 importers)', () => {
  it.each(DELETED_MOTION_COMPONENTS)('components/ui/%s.tsx does not exist', (name) => {
    expect(fs.existsSync(path.join(root, 'components/ui', `${name}.tsx`))).toBe(false);
  });

  it('no file imports any of the 16 deleted component paths, by any specifier', () => {
    // `@/components/ui/marquee` is only one of the ways back in: a sibling inside
    // `components/ui` writes `./marquee`, a file one directory over writes
    // `../ui/marquee`, and all three resolve to the same deleted module. So the
    // specifier is RESOLVED against the importing file rather than matched as a
    // prefix - which also keeps `@/partials/common/avatar-group`, a different
    // component that happens to share a filename, out of the offender list.
    const deleted = new Set(DELETED_MOTION_COMPONENTS.map((name) => `components/ui/${name}`));
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      const dir = path.posix.dirname(file);
      const src = fs.readFileSync(path.join(root, file), 'utf8');
      for (const [, quoted] of src.matchAll(/(?:from|import\(|require\()\s*['"]([^'"]+)['"]/g)) {
        const resolved = quoted.startsWith('.')
          ? path.posix.normalize(path.posix.join(dir, quoted))
          : quoted.startsWith('@/')
            ? quoted.slice(2)
            : null;
        if (resolved && deleted.has(resolved.replace(/\.[jt]sx?$/, ''))) {
          offenders.push(`${file} -> ${quoted}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
