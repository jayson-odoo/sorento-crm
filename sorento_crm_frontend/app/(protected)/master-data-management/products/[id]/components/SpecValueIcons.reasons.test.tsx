/**
 * SPEC-ICON-COMBINED FU F1: each conditioned icon's "shown because ..." hint is the full text on
 * its own line under the value: wrapping, never truncated or width-capped.
 */
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { SpecValueIcons } from './SpecValueIcons';

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

const ICONS = [
  { id: 'a', name: 'S trap 150mm', url: null },
  { id: 'b', name: 'S trap 150mm SUS', url: null },
];
const REASONS = {
  a: 'Trap type = S trap',
  b: 'Trap type = S trap, Steel grade = 304 stainless steel',
};

describe('FU F1 SpecValueIcons hints', () => {
  it('renders one full-text hint per conditioned icon with no truncate or max-width class', () => {
    const { container } = render(
      <SpecValueIcons specKey="trap_length" label="Trap length" icons={ICONS} reasons={REASONS} canManage={false} />,
    );
    const hints = [...container.querySelectorAll('[data-spec-icon-reason]')] as HTMLElement[];
    expect(hints.map((h) => h.textContent)).toEqual([
      'shown because Trap type = S trap',
      'shown because Trap type = S trap, Steel grade = 304 stainless steel',
    ]);
    for (const hint of hints) {
      expect(hint.className).not.toMatch(/truncate|max-w-/);
      expect(hint.className).toContain('text-muted-foreground');
      // The Value cell is `truncate` (nowrap, inherited) in a resizable grid: the hint must undo it.
      expect(hint.className).toContain('whitespace-normal');
      expect(hint.className).toContain('break-words');
    }
  });

  it('puts the hints on their own line, apart from the icon group', () => {
    const { container } = render(
      <SpecValueIcons specKey="trap_length" label="Trap length" icons={ICONS} reasons={REASONS} canManage={false} />,
    );
    const hint = container.querySelector('[data-spec-icon-reason]') as HTMLElement;
    const pictures = container.querySelector('[data-spec-icon]') as HTMLElement;
    expect(hint.parentElement).not.toBe(pictures.parentElement);
  });
});
