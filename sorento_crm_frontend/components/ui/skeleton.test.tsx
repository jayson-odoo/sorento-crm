/**
 * M5-01/M5-02 review N1 - `Skeleton` gains `asChild`, for the two callers
 * (`AttachmentDetailModal.tsx`, `ScenarioDiffSheet.tsx`) whose placeholder sits
 * inside a `<h2>`/`<p>` (phrasing content only) and so cannot take the shared
 * `div`. Before this they hand-rolled the same `animate-pulse rounded-md bg-accent`
 * classes on a bare `span`, carrying none of `Skeleton`'s own `data-slot` marker.
 */
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Skeleton } from './skeleton';

describe('Skeleton', () => {
  it('renders a div by default, with the shared placeholder classes and data-slot', () => {
    const { container } = render(<Skeleton className="h-4 w-24" />);
    const el = container.firstElementChild as HTMLElement;
    expect(el.tagName).toBe('DIV');
    expect(el.dataset.slot).toBe('skeleton');
    expect(el.className).toContain('animate-pulse');
    expect(el.className).toContain('h-4');
  });

  it('asChild renders onto the child element instead of a div, keeping data-slot', () => {
    const { container } = render(
      <Skeleton asChild className="inline-block h-5 w-20 rounded-full align-middle">
        <span />
      </Skeleton>,
    );
    const el = container.firstElementChild as HTMLElement;
    expect(el.tagName).toBe('SPAN');
    expect(el.dataset.slot).toBe('skeleton');
    expect(el.className).toContain('animate-pulse');
    expect(el.className).toContain('rounded-full');
  });
});
