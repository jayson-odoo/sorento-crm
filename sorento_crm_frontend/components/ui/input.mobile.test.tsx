import fs from 'node:fs';
import path from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Input } from './input';

/**
 * M6-03: iOS Safari auto-zooms the page when a focused input renders under
 * 16px - the default (`md`) field size was 13px, so tapping any ordinary
 * text box on a phone zoomed the whole page in and the reader had to pinch
 * back out to keep working. `pointer-coarse:` only raises it on a touch
 * device; the desktop 13px is untouched (pointer: fine keeps its own rule).
 */
describe('Input mobile text size (M6-03)', () => {
  it('the default size renders at 16px under a coarse pointer', () => {
    render(<Input placeholder="x" />);
    const el = screen.getByPlaceholderText('x');
    expect(el.className).toContain('pointer-coarse:text-base');
  });

  it('lg and sm sizes are untouched (already >=16px, or a deliberately dense field)', () => {
    const { rerender } = render(<Input placeholder="x" variant="lg" />);
    expect(screen.getByPlaceholderText('x').className).not.toContain('pointer-coarse:text-base');
    rerender(<Input placeholder="x" variant="sm" />);
    expect(screen.getByPlaceholderText('x').className).not.toContain('pointer-coarse:text-base');
  });
});

describe('no maximum-scale anywhere (M6-03)', () => {
  function sourceFiles(): string[] {
    const out: string[] = [];
    const walk = (dir: string) => {
      if (!fs.existsSync(dir)) return;
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name === 'node_modules' || entry.name === '.next') continue;
          walk(full);
        } else if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.includes('.test.')) {
          out.push(full);
        }
      }
    };
    walk('app');
    walk('components');
    return out;
  }

  it('no file declares a viewport restriction of that kind', () => {
    const offenders = sourceFiles().filter((file) =>
      fs.readFileSync(file, 'utf8').includes('maximum-scale'),
    );
    expect(offenders).toEqual([]);
  });
});
