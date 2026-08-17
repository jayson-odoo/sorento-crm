/**
 * P4 - the money difference at the top of the confirm screen.
 *
 * The distinction being pinned here is the one that decides whether people trust the banner:
 * an unexplained gap between our sum and the printed total is an alarm, while the gap a
 * person themselves created by accepting a cancellation is a fact. Both are stated; only one
 * is a fault.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { POVersion, POVersionLine } from '../../_shared/types/poIntake.types';
import { POIntakeTotalsBanner } from './POIntakeTotalsBanner';

function line(overrides: Partial<POVersionLine> = {}): POVersionLine {
  return {
    id: 'l1',
    line_no: 1,
    stock_code_raw: 'SRTWC8613-RL',
    description_raw: 'RIMLESS CLOSE COUPLED WC',
    qty: '927',
    uom_raw: 'SETS',
    unit_price: '392.85',
    amount: '364171.95',
    arithmetic_ok: true,
    is_cancelled: false,
    resolved_product_id: 'prod-1',
    resolved_product_code: 'SRTWC8613-RL',
    resolution_source: 'code',
    page_no: 1,
    ...overrides,
  };
}

function version(overrides: Partial<POVersion> = {}): POVersion {
  return {
    id: 'v1',
    purchase_order_id: 'po1',
    version_no: 1,
    extraction_state: 'done',
    extraction_error: null,
    extraction_model: 'gemini-2.5-flash',
    page_count: 10,
    document_url: null,
    header: {
      po_number: 'HQ/26/01/041',
      po_date: '2026-01-19',
      term_days: 60,
      sales_person: null,
      customer_order_ref: null,
      admin_ref: 'PS26-0143',
      remark: null,
    },
    totals: {
      extracted_total: '364171.95',
      lines_total: '364171.95',
      arithmetic_passed: 1,
      arithmetic_total: 1,
    },
    lines: [line()],
    annotations: [],
    confirmed_at: null,
    ...overrides,
  };
}

describe('POIntakeTotalsBanner', () => {
  it('says the two totals agree, in money', () => {
    render(<POIntakeTotalsBanner version={version()} />);

    expect(
      screen.getByText(/matches the document total, RM 364,171\.95/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAttribute('data-tone', 'match');
  });

  it('states the difference as an amount before anything else when they disagree', () => {
    render(
      <POIntakeTotalsBanner
        version={version({
          totals: {
            extracted_total: '1810640.62',
            lines_total: '1800000.00',
            arithmetic_passed: 52,
            arithmetic_total: 52,
          },
        })}
      />,
    );

    expect(
      screen.getByText(/RM 10,640\.62 below the total printed on the document/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Document total RM 1,810,640\.62, our sum RM 1,800,000\.00/),
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAttribute('data-tone', 'mismatch');
  });

  it('reads a gap that is exactly the cancelled lines as a fact, not a fault', () => {
    render(
      <POIntakeTotalsBanner
        version={version({
          lines: [
            line(),
            line({ id: 'l2', line_no: 7, amount: '600.00', is_cancelled: true }),
          ],
          totals: {
            extracted_total: '364771.95',
            lines_total: '364171.95',
            arithmetic_passed: 2,
            arithmetic_total: 2,
          },
        })}
      />,
    );

    expect(
      screen.getByText(/RM 600\.00 below the document total, which is the 1 cancelled line/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAttribute('data-tone', 'explained');
  });

  it('says the document total could not be read rather than implying a clean check', () => {
    render(
      <POIntakeTotalsBanner
        version={version({
          totals: {
            extracted_total: null,
            lines_total: '364171.95',
            arithmetic_passed: 1,
            arithmetic_total: 1,
          },
        })}
      />,
    );

    expect(
      screen.getByText(/The document's own total could not be read/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Our sum of the lines is RM 364,171\.95/)).toBeInTheDocument();
  });

  it('counts the lines that do not multiply out, with the right verb', () => {
    const { rerender } = render(
      <POIntakeTotalsBanner
        version={version({
          totals: {
            extracted_total: '364171.95',
            lines_total: '364171.95',
            arithmetic_passed: 51,
            arithmetic_total: 52,
          },
        })}
      />,
    );
    expect(screen.getByText('1 line does not multiply out.')).toBeInTheDocument();

    rerender(
      <POIntakeTotalsBanner
        version={version({
          totals: {
            extracted_total: '364171.95',
            lines_total: '364171.95',
            arithmetic_passed: 49,
            arithmetic_total: 52,
          },
        })}
      />,
    );
    expect(screen.getByText('3 lines do not multiply out.')).toBeInTheDocument();
  });

  it('offers a way to the first problem line only when there is one', () => {
    const onJump = vi.fn();
    const { rerender } = render(
      <POIntakeTotalsBanner version={version()} onJumpToProblem={onJump} />,
    );
    expect(screen.queryByRole('button', { name: /first problem line/i })).toBeNull();

    rerender(
      <POIntakeTotalsBanner
        version={version({
          totals: {
            extracted_total: '1810640.62',
            lines_total: '1800000.00',
            arithmetic_passed: 51,
            arithmetic_total: 52,
          },
        })}
        onJumpToProblem={onJump}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /first problem line/i }));
    expect(onJump).toHaveBeenCalledTimes(1);
  });
});
