/**
 * M2-06 - the remaining keyframe menu surfaces move to the shared menu
 * spring: `DropdownMenuSubContent`, `ContextMenuContent`, `ContextMenuSubContent`,
 * `HoverCardContent` and `MenubarContent` (plus `MenubarSubContent`, migrated
 * alongside it) carry no `animate-in`/`animate-out` tw-animate classes and
 * render a `motion.div` on `surfaceTransition(reduced, 'menu')`.
 *
 * These read the component SOURCE rather than rendering each primitive:
 * ContextMenu opens on a real right-click event, Menubar's per-item Content
 * has no externally-controllable open state (see the comment in
 * menubar.tsx), and a source check is what stays true regardless of how a
 * given primitive is driven open.
 */
import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';

const root = path.resolve(__dirname, '..', '..');
const read = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

const files = [
  'components/ui/dropdown-menu.tsx',
  'components/ui/context-menu.tsx',
  'components/ui/hover-card.tsx',
  'components/ui/menubar.tsx',
];

describe('Menu-family surfaces carry no tw-animate keyframe classes (M2-06)', () => {
  for (const file of files) {
    it(`${file} has no animate-in/animate-out/zoom classes`, () => {
      const source = read(file);
      expect(source).not.toContain('animate-in');
      expect(source).not.toContain('animate-out');
      expect(source).not.toContain('zoom-in-95');
      expect(source).not.toContain('zoom-out-95');
      expect(source).not.toContain('slide-in-from');
    });

    it(`${file} renders a motion.div on the menu spring`, () => {
      const source = read(file);
      expect(source).toContain('motion.div');
      expect(source).toContain("surfaceTransition(prefersReducedMotion, 'menu')");
    });
  }
});
