/**
 * DATE-PICKER-UNIFY: the filters dropdown (`DropdownMenuContent w-72 p-3`, 264px inner) sizes
 * itself. A fixed width on the `content:` wrapper (288px with `w-72`) overflows it and clips the
 * date range's calendar button, so the wrapper must set no fixed width and fill the dropdown.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

describe('Chat History filters content wrapper', () => {
  it('sets no fixed width class', () => {
    const src = fs.readFileSync(path.join(__dirname, 'page.tsx'), 'utf8');
    const match = /content:\s*\(\s*<div className="([^"]*)"/.exec(src);
    expect(match, 'filters content wrapper div not found').not.toBeNull();
    expect(match![1].split(/\s+/).filter((c) => /^w-(\d|\[|px)/.test(c))).toEqual([]);
  });
});
