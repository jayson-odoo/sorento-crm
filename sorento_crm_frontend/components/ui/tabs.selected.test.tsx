/**
 * TOGGLE-SELECTED - a pill tab strip is a view toggle (DESIGN-LANGUAGE.md section 4: pills are
 * reserved for a toggle that is not navigation), so its selected option is the primary colour,
 * the same as a selected ToggleGroupItem. The line strip, which IS navigation, keeps its
 * primary underline and gains no fill.
 *
 * Plan: documentation/plans/design-system/PLAN-toggle-selected-20oct.md
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Tabs, TabsList, TabsTrigger } from './tabs';

function classOf(el: Element | null) {
  return el?.getAttribute('class') ?? '';
}

function renderStrip(variant: 'default' | 'button' | 'line') {
  render(
    <Tabs defaultValue="desktop">
      <TabsList variant={variant}>
        <TabsTrigger value="desktop">Desktop</TabsTrigger>
        <TabsTrigger value="mobile">Mobile</TabsTrigger>
      </TabsList>
    </Tabs>,
  );
  return screen.getByRole('tab', { name: 'Desktop' });
}

describe('a selected pill tab is the primary colour', () => {
  for (const variant of ['default', 'button'] as const) {
    it(`the active ${variant} trigger is primary with readable text and icon`, () => {
      const active = renderStrip(variant);
      expect(active.getAttribute('data-state')).toBe('active');
      const cls = classOf(active);
      expect(cls).toContain('data-[state=active]:bg-primary');
      expect(cls).toContain('data-[state=active]:text-primary-foreground');
      expect(cls).toContain('[&[data-state=active]_svg]:text-primary-foreground');
      expect(cls).not.toContain('data-[state=active]:bg-popover');
      expect(cls).not.toContain('data-[state=active]:bg-accent');
    });
  }

  it('the line strip keeps its underline and no fill', () => {
    const cls = classOf(renderStrip('line'));
    expect(cls).toContain('data-[state=active]:border-primary');
    expect(cls).not.toContain('data-[state=active]:bg-primary');
  });
});
