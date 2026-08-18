/**
 * Stage 1B - the whole SO's one pre-confirmation state (AC-A03, AC-G02).
 *
 * Nothing here is per line, so the only two labels this pill may ever say are the two
 * values `ReviewState` can hold, plus the exception count that names how far a row is from
 * clearing. Absent state renders nothing, so a row on a backend that has not shipped the
 * field yet is unchanged rather than showing a broken pill.
 */
import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReviewStatePill } from './ReviewStatePill';

describe('ReviewStatePill', () => {
  it('reads Awaiting reconciliation for that state', () => {
    render(<ReviewStatePill state="awaiting_reconciliation" />);

    expect(screen.getByText('Awaiting reconciliation')).toBeInTheDocument();
  });

  it('reads Needs CS review for that state, never confirmed or purchasing-ready', () => {
    render(<ReviewStatePill state="needs_cs_review" />);

    expect(screen.getByText('Needs CS review')).toBeInTheDocument();
    expect(screen.queryByText(/confirmed|partial|purchasing/i)).not.toBeInTheDocument();
  });

  it('appends the exception count, pluralized', () => {
    render(<ReviewStatePill state="awaiting_reconciliation" exceptionCount={3} />);

    expect(screen.getByText('Awaiting reconciliation · 3 exceptions')).toBeInTheDocument();
  });

  it('does not pluralize a single exception', () => {
    render(<ReviewStatePill state="awaiting_reconciliation" exceptionCount={1} />);

    expect(screen.getByText('Awaiting reconciliation · 1 exception')).toBeInTheDocument();
  });

  it('never shows a bare zero count', () => {
    render(<ReviewStatePill state="needs_cs_review" exceptionCount={0} />);

    expect(screen.getByText('Needs CS review')).toBeInTheDocument();
    expect(screen.queryByText(/exception/i)).not.toBeInTheDocument();
  });

  it('shows the label alone when no count is supplied', () => {
    render(<ReviewStatePill state="needs_cs_review" />);

    expect(screen.getByText('Needs CS review')).toBeInTheDocument();
    expect(screen.queryByText(/exception/i)).not.toBeInTheDocument();
  });

  it('renders nothing when the state is absent', () => {
    const { container } = render(<ReviewStatePill state={undefined} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the state is null', () => {
    const { container } = render(<ReviewStatePill state={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});
