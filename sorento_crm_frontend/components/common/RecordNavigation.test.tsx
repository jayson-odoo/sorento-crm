/**
 * Tests for the dual-mode RecordNavigation pager.
 *
 * Focus: IDs mode (the standard for backend-driven list pagers per
 * docs/plans/PLAN-record-navigation-standardization.md). Covers:
 *  - renders "index / total"
 *  - Prev disabled when prevId == null; Next disabled when nextId == null
 *  - "— / total" when index is null (out-of-position)
 *  - isLoading -> "… / total"
 * Plus a smoke test that the legacy array (list) mode still renders, so the
 * dual-mode contract isn't broken.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import RecordNavigation from './RecordNavigation';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

describe('RecordNavigation — IDs mode', () => {
  it('renders the "index / total" counter', () => {
    render(
      <RecordNavigation
        basePath="/complaint-management/complaints"
        prevId="p1"
        nextId="n1"
        currentIndex={2}
        totalCount={23}
      />,
    );
    // currentIndex is 0-based; rendered as currentIndex + 1.
    expect(screen.getByText('3 / 23')).toBeInTheDocument();
  });

  it('disables Prev when prevId is null', () => {
    render(
      <RecordNavigation
        basePath="/x"
        prevId={null}
        nextId="n1"
        currentIndex={0}
        totalCount={5}
      />,
    );
    expect(screen.getByLabelText('Previous record')).toBeDisabled();
    expect(screen.getByLabelText('Next record')).not.toBeDisabled();
  });

  it('disables Next when nextId is null', () => {
    render(
      <RecordNavigation
        basePath="/x"
        prevId="p1"
        nextId={null}
        currentIndex={4}
        totalCount={5}
      />,
    );
    expect(screen.getByLabelText('Next record')).toBeDisabled();
    expect(screen.getByLabelText('Previous record')).not.toBeDisabled();
  });

  it('single-record set (both null) disables both chevrons and reads "1 / 1"', () => {
    render(
      <RecordNavigation
        basePath="/x"
        prevId={null}
        nextId={null}
        currentIndex={0}
        totalCount={1}
      />,
    );
    expect(screen.getByText('1 / 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Previous record')).toBeDisabled();
    expect(screen.getByLabelText('Next record')).toBeDisabled();
  });

  it('renders "— / total" when index is null (position unknown)', () => {
    render(
      <RecordNavigation
        basePath="/x"
        prevId="p1"
        nextId="n1"
        totalCount={23}
        // currentIndex omitted -> index unknown
      />,
    );
    expect(screen.getByText('— / 23')).toBeInTheDocument();
  });

  it('renders "… / total" while loading', () => {
    render(
      <RecordNavigation
        basePath="/x"
        prevId={null}
        nextId={null}
        currentIndex={3}
        totalCount={23}
        isLoading
      />,
    );
    expect(screen.getByText('… / 23')).toBeInTheDocument();
  });

  it('navigates via router.push on Next click in IDs mode', () => {
    push.mockClear();
    render(
      <RecordNavigation
        basePath="/complaint-management/complaints"
        prevId="p1"
        nextId="n1"
        currentIndex={1}
        totalCount={5}
      />,
    );
    fireEvent.click(screen.getByLabelText('Next record'));
    expect(push).toHaveBeenCalledWith('/complaint-management/complaints/n1');
  });

  it('calls onSelect instead of router when provided', () => {
    const onSelect = vi.fn();
    render(
      <RecordNavigation
        basePath="/x"
        prevId="p1"
        nextId="n1"
        currentIndex={1}
        totalCount={5}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByLabelText('Previous record'));
    expect(onSelect).toHaveBeenCalledWith('p1');
  });
});

describe('RecordNavigation — list (array) mode still works', () => {
  it('computes prev/next from items and renders the counter', () => {
    const items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
    render(
      <RecordNavigation
        basePath="/x"
        currentId="b"
        items={items}
        totalCount={3}
      />,
    );
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    expect(screen.getByLabelText('Previous record')).not.toBeDisabled();
    expect(screen.getByLabelText('Next record')).not.toBeDisabled();
  });
});
