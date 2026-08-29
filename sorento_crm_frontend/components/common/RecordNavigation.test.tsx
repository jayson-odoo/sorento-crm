/**
 * The chevrons and the counter, now that `RecordNavigation` is presentational.
 *
 * Position and ends are the caller's business (`ListPager` for a URL-walked
 * record, the dialog itself for one walked in place), so what is left to prove
 * here is the reading and the disabling:
 * - "index / total", and the two "not known yet" readings
 * - Prev/Next disabled at the ends, and the handlers fired otherwise
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

import RecordNavigation from './RecordNavigation';

const onPrevious = vi.fn();
const onNext = vi.fn();

beforeEach(() => {
  cleanup();
  onPrevious.mockReset();
  onNext.mockReset();
});

function renderPager(props: Partial<React.ComponentProps<typeof RecordNavigation>> = {}) {
  return render(
    <RecordNavigation
      index={2}
      total={7}
      hasPrevious
      hasNext
      onPrevious={onPrevious}
      onNext={onNext}
      ariaLabel="complaint"
      {...props}
    />,
  );
}

describe('RecordNavigation', () => {
  it('renders the "index / total" counter', () => {
    renderPager();

    expect(screen.getByText('2 / 7')).toBeInTheDocument();
  });

  it('reads "- / total" when the record is not on the page', () => {
    renderPager({ index: null });

    expect(screen.getByText('- / 7')).toBeInTheDocument();
  });

  it('reads "… / total" while the page is still loading', () => {
    renderPager({ index: null, isLoading: true });

    expect(screen.getByText('… / 7')).toBeInTheDocument();
  });

  it('disables Previous at the start and Next at the end', () => {
    renderPager({ hasPrevious: false, hasNext: false });

    expect(screen.getByRole('button', { name: 'Previous complaint' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next complaint' })).toBeDisabled();
  });

  it('fires the caller handlers, and nothing else', () => {
    renderPager();

    fireEvent.click(screen.getByRole('button', { name: 'Next complaint' }));
    fireEvent.click(screen.getByRole('button', { name: 'Previous complaint' }));

    expect(onNext).toHaveBeenCalledTimes(1);
    expect(onPrevious).toHaveBeenCalledTimes(1);
  });

  /**
   * The five edit forms render the pager INSIDE their `<form>`, and a `<button>`
   * with no `type` submits it. Next therefore saved the record and ran the form's
   * `onSuccess`, which pushes the read-only route for the SAME id: the reader
   * landed back on the view of the customer they were editing, with the counter
   * unmoved, and the step they asked for never happened.
   */
  it('does not submit the form it is rendered inside', () => {
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <RecordNavigation
          index={1}
          total={50}
          hasPrevious
          hasNext
          onPrevious={onPrevious}
          onNext={onNext}
          ariaLabel="customer"
        />
      </form>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Next customer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Previous customer' }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(onNext).toHaveBeenCalledTimes(1);
    expect(onPrevious).toHaveBeenCalledTimes(1);
  });

  it('names the record type in the chevrons, for a screen reader', () => {
    renderPager({ ariaLabel: 'purchase order' });

    expect(screen.getByRole('button', { name: 'Previous purchase order' })).toBeInTheDocument();
    expect(screen.getByLabelText('purchase order navigation')).toBeInTheDocument();
  });
});
