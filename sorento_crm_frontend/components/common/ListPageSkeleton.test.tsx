/**
 * M5-03 (`PLAN-ui-motion-round2.md` 3.5) - `ListPageSkeleton`'s geometry has
 * to match the real grid it stands in for, or landing on the real page
 * shifts the title and the first row instead of swapping bar-for-content in
 * place.
 *
 * Two things it is measured against:
 * - `components/ui/data-grid-table.tsx`: the body cell is `px-4 py-3
 *   h-[60px]` (`bodyCellSpacingVariants.default`) and the header cell is
 *   `px-4` (`headerCellSpacingVariants.default`).
 * - `components/common/PageHeader.tsx`: `ToolbarHeading` is a plain
 *   `flex-col` (no reverse), and inside it the `<h1>` title (lines 154-161)
 *   comes BEFORE the `<Breadcrumb>` trail (line 162) in DOM order - the
 *   title is on top, the crumb trail sits below it. This is the opposite of
 *   what this slice's own brief and the UAC's M5-03 wording assumed ("the
 *   crumb bar is above the title"); that wording is corrected here against
 *   the measured file rather than carried into the fix, since matching the
 *   real order is the entire point of the test (a skeleton that mimics the
 *   WRONG order would swap positions when the real page lands, which is
 *   the shift M5-03 exists to prevent).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { ListPageSkeleton } from './ListPageSkeleton';

describe('ListPageSkeleton geometry matches the real grid and header (M5-03)', () => {
  it('draws a body row at h-[60px] px-4, matching data-grid-table.tsx', () => {
    const { container } = render(<ListPageSkeleton rows={2} />);
    const rows = container.querySelectorAll('[data-slot="list-skeleton-row"]');
    expect(rows.length).toBe(2);
    for (const row of rows) {
      expect(row.className).toContain('h-[60px]');
      expect(row.className).toContain('px-4');
      expect(row.className).not.toContain('px-5');
    }
  });

  it('draws the header row at px-4, matching data-grid-table.tsx', () => {
    const { container } = render(<ListPageSkeleton />);
    const header = container.querySelector('[data-slot="list-skeleton-header-row"]');
    expect(header).not.toBeNull();
    expect(header!.className).toContain('px-4');
    expect(header!.className).not.toContain('px-5');
  });

  it('renders the title bar before the crumb bar, matching PageHeader.tsx DOM order', () => {
    const { container } = render(<ListPageSkeleton />);
    const title = container.querySelector('[data-testid="list-skeleton-title"]');
    const crumb = container.querySelector('[data-testid="list-skeleton-crumb"]');
    expect(title).not.toBeNull();
    expect(crumb).not.toBeNull();

    // DOCUMENT_POSITION_FOLLOWING: crumb comes AFTER title in the DOM.
    const position = title!.compareDocumentPosition(crumb!);
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('passes rows through', () => {
    const { container } = render(<ListPageSkeleton rows={3} />);
    expect(container.querySelectorAll('[data-slot="list-skeleton-row"]').length).toBe(3);
  });
});
