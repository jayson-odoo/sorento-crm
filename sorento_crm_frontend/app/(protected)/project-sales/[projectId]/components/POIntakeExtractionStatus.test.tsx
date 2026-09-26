/**
 * W3 (PR #1265 round 3): the read progress bar the PO screen and the schedule screen share.
 *
 * Owner hand test, 26 Sep: "the PO desing is ok like it got progress bar, why this one no
 * progreess bar". One element for both reads, and while pages are landing the bar is the pages
 * read of the total, so it moves as the worker reports each page.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { POIntakeExtractionProgress } from './POIntakeExtractionStatus';

function progress(overrides: Partial<React.ComponentProps<typeof POIntakeExtractionProgress>['version']>) {
  return {
    extraction_state: 'running' as const,
    page_count: 7,
    pages_extracted: 0,
    extraction_started_at: null,
    ...overrides,
  };
}

describe('POIntakeExtractionProgress', () => {
  it('moves the bar with the pages read, as the worker reports them', () => {
    const { rerender } = render(
      <POIntakeExtractionProgress version={progress({ pages_extracted: 3 })} />,
    );
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '43');
    expect(screen.getByText('Page 4 of 7')).toBeInTheDocument();

    rerender(<POIntakeExtractionProgress version={progress({ pages_extracted: 5 })} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '71');
    expect(screen.getByText('Page 6 of 7')).toBeInTheDocument();
  });

  it('shows a sliver, not an empty bar, before the first page lands', () => {
    render(<POIntakeExtractionProgress version={progress({ pages_extracted: 0 })} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '5');
  });

  it('keeps the bar on a queued read, with the page count and no invented page', () => {
    render(
      <POIntakeExtractionProgress
        version={progress({ extraction_state: 'queued', pages_extracted: 0 })}
      />,
    );
    expect(screen.getByText('Waiting to be read')).toBeInTheDocument();
    expect(screen.getByText('7 pages')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
    expect(screen.queryByText(/Page \d+ of/)).toBeNull();
  });
});
