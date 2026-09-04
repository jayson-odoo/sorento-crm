import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

/**
 * M6-04: one `<Toaster>` mount, top-center, for the whole app. Rendering
 * `ClientProviders` needs the full provider stack (auth, settings, theme,
 * i18n, modules) standing up, which is a lot of mocking for what is really a
 * one-line source fact - so this reads it the way `mobile-one-offs.inventory`
 * does, and the inventory test above is what keeps the OTHER half (no file
 * anywhere else imports `sonner` to mount a second one) honest.
 */
describe('ClientProviders Toaster mount (M6-04)', () => {
  it('mounts exactly one <Toaster position="top-center">', () => {
    const src = fs.readFileSync(path.join(__dirname, 'ClientProviders.tsx'), 'utf8');
    expect(src).toContain('<Toaster position="top-center" />');
  });

  it('is the only <Toaster mount in app/ or components/', () => {
    const mounts: string[] = [];
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name === 'node_modules' || entry.name === '.next') continue;
          walk(full);
        } else if (entry.name.endsWith('.tsx') && !entry.name.includes('.test.')) {
          const src = fs.readFileSync(full, 'utf8');
          if (/<Toaster[\s/>]/.test(src)) mounts.push(full);
        }
      }
    };
    walk(path.join(__dirname, '..', 'app'));
    walk(path.join(__dirname, '..', 'components'));
    expect(mounts).toEqual([path.join(__dirname, 'ClientProviders.tsx')]);
  });
});
