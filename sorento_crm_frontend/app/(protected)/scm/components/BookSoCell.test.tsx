/**
 * BookSoCell - PO-LINK-HISTORY: the S/O value opens a popover saying when and how the
 * AutoCount sync linked it (`book_so_link`, the line's latest S/O link audit event).
 *
 * Owner, 4 Nov 2026: "can i see the audit trails of when is this linked in the UI?"
 * Plan: documentation/plans/procurement/PLAN-po-link-history-04nov.md (card 3).
 */
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import { BookSoCell, type BookSoLinkage } from './BookSoCell';

afterEach(cleanup);

const TRIGGER = 'S/O link history';

function open(line: BookSoLinkage) {
  render(<BookSoCell line={line} />);
  fireEvent.click(screen.getByRole('button', { name: TRIGGER }));
}

describe('BookSoCell - link history popover', () => {
  it('has no popover when no link event was ever recorded', () => {
    render(<BookSoCell line={{ book_so_number: 'SO422492', book_so_link: null }} />);

    expect(screen.getByText('SO422492')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: TRIGGER })).toBeNull();
  });

  it('says the AutoCount sync linked it, when, and the S/O it replaced', () => {
    open({
      book_so_number: 'SO422492',
      book_so_link: {
        // Naive UTC, as the audit log stores it: 06:05 UTC is 2:05 pm in Malaysia.
        changed_at: '2026-09-04T06:05:00',
        estimated: false,
        previous_linked: true,
        previous_so_number: 'SO411111',
      },
    });

    expect(screen.getByText('Linked by AutoCount sync')).toBeInTheDocument();
    expect(screen.getByText(/04\/09\/2026/)).toBeInTheDocument();
    expect(screen.getByText('SO411111')).toBeInTheDocument();
  });

  it('says "Not linked" when the line had no S/O before', () => {
    open({
      book_so_number: 'SO422492',
      book_so_link: {
        changed_at: '2026-09-04T06:05:00',
        estimated: false,
        previous_linked: false,
        previous_so_number: null,
      },
    });

    expect(screen.getByText('Not linked')).toBeInTheDocument();
  });

  it('names a previous S/O this system does not hold the way the cell does', () => {
    open({
      book_so_number: 'SO422492',
      book_so_link: {
        changed_at: '2026-09-04T06:05:00',
        estimated: false,
        previous_linked: true,
        previous_so_number: null,
      },
    });

    expect(screen.getByText('Linked, not held')).toBeInTheDocument();
  });

  it('states a backfilled time as an upper bound, never as the moment', () => {
    open({
      book_so_number: 'SO422492',
      book_so_link: {
        changed_at: '2026-09-02T01:30:00',
        estimated: true,
        previous_linked: null,
        previous_so_number: null,
      },
    });

    expect(screen.getByText(/Linked on or before 02\/09\/2026/)).toBeInTheDocument();
    expect(screen.getByText('Earlier history not recorded')).toBeInTheDocument();
    expect(screen.queryByText('Linked by AutoCount sync')).toBeNull();
  });

  it('opens on a dash too, when the sync unlinked the line', () => {
    open({
      book_so_number: null,
      book_so_unresolved: false,
      book_so_link: {
        changed_at: '2026-09-04T06:05:00',
        estimated: false,
        previous_linked: true,
        previous_so_number: 'SO411111',
      },
    });

    expect(screen.getByText('Unlinked by AutoCount sync')).toBeInTheDocument();
    expect(screen.getByText('SO411111')).toBeInTheDocument();
  });
});
