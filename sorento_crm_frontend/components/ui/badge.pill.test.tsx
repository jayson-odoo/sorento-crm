/**
 * S1-08 - the pill.
 *
 * One shape for every status and tag in the product: a round tinted pill, 24px
 * tall at `md`, with a 6px dot when it carries a status. jsdom has no layout, so
 * what is pinned here is the class contract the whole app inherits, plus the two
 * behaviours a call site can observe: `status` resolves its own colour, and the
 * retired `ghost` appearance no longer renders as bare text.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Badge } from './badge';
import { getStatusBadgeVariant } from '@/lib/status-badge';

describe('Badge (S1-08)', () => {
  it('S1-08: is a round tinted pill 24px tall by default', () => {
    render(<Badge>Draft</Badge>);
    const badge = screen.getByText('Draft');

    expect(badge).toHaveClass('rounded-full');
    expect(badge).toHaveClass('h-6');
    // Tinted fill + matching text, not the old solid block.
    expect(badge.className).not.toContain('bg-primary ');
    expect(badge.className).toMatch(/bg-\[var\(--color-primary-soft/);
  });

  it('S1-08: `sm` is the only smaller pill and stays round', () => {
    render(<Badge size="sm">Tag</Badge>);
    const badge = screen.getByText('Tag');
    expect(badge).toHaveClass('rounded-full');
    expect(badge).toHaveClass('h-5');
  });

  it('S1-08: `status` renders a 6px dot before the label', () => {
    const { container } = render(<Badge status="pending">Pending</Badge>);
    const dot = container.querySelector('[data-slot="badge-dot"]');

    expect(dot).not.toBeNull();
    expect(dot).toHaveClass('size-1.5');
    // The dot precedes the label.
    expect(screen.getByText('Pending').firstElementChild).toBe(dot);
  });

  it('S1-08: `status` takes its colour from getStatusBadgeVariant', () => {
    expect(getStatusBadgeVariant('cancelled')).toBe('destructive');

    render(<Badge status="cancelled">Cancelled</Badge>);
    expect(screen.getByText('Cancelled').className).toMatch(/--color-destructive-soft/);
  });

  it('S1-08: `status` is not forwarded to the DOM', () => {
    render(<Badge status="approved">Approved</Badge>);
    expect(screen.getByText('Approved')).not.toHaveAttribute('status');
  });

  it('S1-08: a plain Badge carries no dot', () => {
    const { container } = render(<Badge>Tag only</Badge>);
    expect(container.querySelector('[data-slot="badge-dot"]')).toBeNull();
  });

  it('S1-08: the ghost appearance no longer exists - it renders as light', () => {
    const { container: ghost } = render(<Badge appearance="ghost">X</Badge>);
    const { container: light } = render(<Badge appearance="light">X</Badge>);

    const ghostClass = ghost.firstElementChild!.className;
    expect(ghostClass).toBe(light.firstElementChild!.className);
    expect(ghostClass).not.toContain('bg-transparent');
  });

  it('S1-08: count badges (shape="circle") render unchanged - circular and solid', () => {
    render(<Badge shape="circle">9</Badge>);
    const badge = screen.getByText('9');

    expect(badge).toHaveClass('rounded-full');
    // Solid, not tinted: a tinted "9" reads as a status rather than a count.
    expect(badge).toHaveClass('bg-primary');
    expect(badge.className).not.toMatch(/--color-primary-soft/);
  });

  it('S1-08: a count badge that asks for a tint still gets one', () => {
    render(
      <Badge shape="circle" appearance="light">
        9
      </Badge>,
    );
    expect(screen.getByText('9').className).toMatch(/--color-primary-soft/);
  });
});
