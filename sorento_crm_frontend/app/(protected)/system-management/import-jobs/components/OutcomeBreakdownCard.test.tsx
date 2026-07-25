import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OutcomeBreakdownCard } from './OutcomeBreakdownCard';
import type { ImportJobResultEnvelope } from '../types/importJob.types';

/** Shaped after the job that motivated this work. */
const ENVELOPE: ImportJobResultEnvelope = {
  message: 'Delivery order detail import completed',
  counts: { total: 4231, processed: 4231, successful: 3447, failed: 5, skipped: 779 },
  breakdown: {
    successful: [{ code: 'created', label: 'Order line created', count: 3447, top_values: [] }],
    skipped: [
      { code: 'order_not_found', label: 'Order not found', count: 751, top_values: [] },
      {
        code: 'product_not_found',
        label: 'Product not found',
        count: 15,
        top_values: [
          { value: 'SRTWC8354-SH-UF-150', count: 4 },
          { value: 'SRTWC8354-SH-UF-P', count: 3 },
        ],
      },
    ],
    failed: [{ code: 'row_error', label: 'Row could not be written', count: 5, top_values: [] }],
  },
  rows_truncated: false,
  rows_total: 4231,
};

describe('OutcomeBreakdownCard', () => {
  it('shows every reason with its exact count', () => {
    render(<OutcomeBreakdownCard result={ENVELOPE} />);

    expect(screen.getByText('Order line created')).toBeInTheDocument();
    // 3,447 shows twice: once as the group total, once as its only reason.
    expect(screen.getAllByText('3,447')).toHaveLength(2);
    expect(screen.getByText('Order not found')).toBeInTheDocument();
    expect(screen.getByText('751')).toBeInTheDocument();
    expect(screen.getByText('Row could not be written')).toBeInTheDocument();
  });

  it('lists the distinct offending values behind a reason', () => {
    render(<OutcomeBreakdownCard result={ENVELOPE} />);
    expect(screen.getByText('SRTWC8354-SH-UF-150')).toBeInTheDocument();
    expect(screen.getByText('×4')).toBeInTheDocument();
    expect(screen.getByText('SRTWC8354-SH-UF-P')).toBeInTheDocument();
  });

  it('reports each group total', () => {
    render(<OutcomeBreakdownCard result={ENVELOPE} />);
    // Skipped group total = 751 + 15
    expect(screen.getByText('766')).toBeInTheDocument();
  });

  it('emits the clicked reason so the rows grid can filter to it', () => {
    const onSelectCode = vi.fn();
    render(<OutcomeBreakdownCard result={ENVELOPE} onSelectCode={onSelectCode} />);

    fireEvent.click(screen.getByText('Product not found'));
    expect(onSelectCode).toHaveBeenCalledWith('product_not_found', 'skipped');
  });

  it('renders an explicit empty state per group rather than hiding it', () => {
    render(
      <OutcomeBreakdownCard
        result={{
          ...ENVELOPE,
          breakdown: { successful: [], skipped: [], failed: [] },
        }}
      />,
    );
    expect(screen.getByText('Nothing was written by this job.')).toBeInTheDocument();
    expect(screen.getByText('No rows were skipped.')).toBeInTheDocument();
    expect(screen.getByText('No rows failed.')).toBeInTheDocument();
  });

  it('falls back gracefully for jobs that predate outcome capture', () => {
    render(<OutcomeBreakdownCard result={{ message: 'legacy', errors: [] }} />);
    expect(screen.getByText(/ran before per-row outcome capture/i)).toBeInTheDocument();
  });

  it('handles a missing result object', () => {
    render(<OutcomeBreakdownCard result={null} />);
    expect(screen.getByText(/ran before per-row outcome capture/i)).toBeInTheDocument();
  });

  it('flags a truncated row capture', () => {
    render(<OutcomeBreakdownCard result={{ ...ENVELOPE, rows_truncated: true }} />);
    expect(screen.getByText('Row capture truncated')).toBeInTheDocument();
  });

  it('marks the active reason', () => {
    const { container } = render(
      <OutcomeBreakdownCard result={ENVELOPE} activeCode="order_not_found" />,
    );
    expect(container.querySelector('.border-primary')).toBeTruthy();
  });
});
