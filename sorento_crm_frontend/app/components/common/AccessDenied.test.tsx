/**
 * UIUX-QUICK-WINS item 7: one shared no-access state. It names who can open the area and
 * offers a way back; no screen hand-rolls "Forbidden - ..." text any more (guard below).
 */
import React from 'react';
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import AccessDenied from './AccessDenied';

describe('AccessDenied', () => {
  it('says who can open it and offers a way back, as a plain (not destructive) button', () => {
    render(<AccessDenied description="Only superadmins can manage companies." />);
    expect(screen.getByRole('heading', { name: "You don't have access to this page" })).toBeInTheDocument();
    expect(screen.getByText('Only superadmins can manage companies.')).toBeInTheDocument();
    const back = screen.getByRole('link', { name: 'Back to dashboard' });
    expect(back).toHaveAttribute('href', '/');
    expect(back.className).not.toMatch(/destructive/);
  });
});

const APP_ROOT = join(import.meta.dirname, '..', '..', '..');

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (['node_modules', '.next', 'e2e', '__testsupport__'].includes(entry.name)) continue;
      out.push(...sourceFiles(full));
      continue;
    }
    if (!/\.tsx?$/.test(entry.name) || /\.test\.tsx?$/.test(entry.name)) continue;
    out.push(full);
  }
  return out;
}

describe('no ad hoc no-access text', () => {
  it('no screen hand-rolls "Forbidden - ..." instead of the shared AccessDenied', () => {
    const files = ['app', 'components'].flatMap((d) => sourceFiles(join(APP_ROOT, d)));
    expect(files.length).toBeGreaterThan(100);
    const hits = files
      .filter((f) => /Forbidden - /.test(readFileSync(f, 'utf8')))
      .map((f) => relative(APP_ROOT, f));
    expect(hits).toEqual([]);
  });
});
