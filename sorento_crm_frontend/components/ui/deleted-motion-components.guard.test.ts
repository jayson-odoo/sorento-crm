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

  it('no file imports any of the 16 deleted component paths', () => {
    const files = sourceFiles();
    const offenders: string[] = [];
    for (const file of files) {
      const src = fs.readFileSync(path.join(root, file), 'utf8');
      for (const name of DELETED_MOTION_COMPONENTS) {
        if (src.includes(`components/ui/${name}'`) || src.includes(`components/ui/${name}"`)) {
          offenders.push(`${file} -> ${name}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
