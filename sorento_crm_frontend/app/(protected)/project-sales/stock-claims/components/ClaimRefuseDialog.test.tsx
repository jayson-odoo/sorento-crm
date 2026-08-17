/**
 * P9 - refusing a stock claim (AC-H4).
 *
 * A refusal is only useful if it says why. Without a reason the asking CS learns nothing
 * except that they now have to make the phone call the claim was meant to replace, so the
 * dialog refuses to send one: the button stays disabled on an empty box and on whitespace,
 * and the reason that does go is the trimmed one.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AllocationClaimRow } from '../../_shared/types/projectAllocation.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

import { ClaimRefuseDialog } from './ClaimRefuseDialog';

function claim(overrides: Partial<AllocationClaimRow> = {}): AllocationClaimRow {
  return {
    id: 'c1',
    state: 'requested',
    qty: '40',
    reason: null,
    from_project_id: 'p1',
    from_project_code: 'PRJ-000001',
    from_project_cs_name: 'Eling',
    to_project_id: 'p2',
    to_project_code: 'PRJ-000042',
    to_project_cs_name: 'Aisyah',
    product_id: 'prod-1',
    product_code: 'SRT382-6',
    product_name: 'SORENTO STAINLESS STEEL FLOOR GRATING',
    warehouse_id: 'wh-kl',
    warehouse_code: 'WH-KL',
    so_line_id: 'l1',
    sales_order_id: 'so-1',
    sales_order_ref: 'PSO-000123',
    line_no: 7,
    delivery_date: '2026-07-01',
    requested_by_name: 'Eling',
    decided_by_name: null,
    decided_at: null,
    created_at: '2026-07-20T02:00:00',
    ...overrides,
  };
}

const onRefuse = vi.fn();
const onDone = vi.fn();

function renderDialog(
  props: { claim?: AllocationClaimRow; submitting?: boolean } = {},
) {
  return render(
    <ClaimRefuseDialog
      claim={props.claim ?? claim()}
      submitting={props.submitting ?? false}
      onDone={onDone}
      onRefuse={onRefuse}
    />,
  );
}

const reasonBox = () => screen.getByLabelText('Why the stock cannot be released');
const refuseButton = () => screen.getByRole('button', { name: 'Refuse' });

beforeEach(() => {
  vi.clearAllMocks();
  onRefuse.mockResolvedValue(undefined);
});

describe('ClaimRefuseDialog', () => {
  it('restates what is being refused, down to the quantity and the location', () => {
    renderDialog();

    expect(screen.getByText('Refuse this claim')).toBeInTheDocument();
    expect(
      screen.getByText('PRJ-000001 asked for 40 SRT382-6 at WH-KL.'),
    ).toBeInTheDocument();
  });

  it('names the person who will read the reason', () => {
    renderDialog();

    expect(screen.getByText('Eling sees this on the line.')).toBeInTheDocument();
  });

  it('still reads as a sentence when the claim carries no product or location', () => {
    renderDialog({
      claim: claim({ product_code: null, warehouse_code: null, from_project_cs_name: null }),
    });

    expect(
      screen.getByText('PRJ-000001 asked for 40 of this product at this location.'),
    ).toBeInTheDocument();
    expect(screen.getByText('The asking CS sees this on the line.')).toBeInTheDocument();
  });

  it('refuses nothing while the reason box is empty', () => {
    renderDialog();

    expect(refuseButton()).toBeDisabled();

    fireEvent.click(refuseButton());
    expect(onRefuse).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
  });

  it('does not accept whitespace as a reason', () => {
    renderDialog();

    fireEvent.change(reasonBox(), { target: { value: '     ' } });

    expect(refuseButton()).toBeDisabled();
    fireEvent.click(refuseButton());
    expect(onRefuse).not.toHaveBeenCalled();
  });

  it('does not accept a reason too short to mean anything', () => {
    renderDialog();

    fireEvent.change(reasonBox(), { target: { value: 'no' } });

    expect(refuseButton()).toBeDisabled();
    expect(onRefuse).not.toHaveBeenCalled();
  });

  it('sends the trimmed reason once one is typed, then closes', async () => {
    renderDialog();

    fireEvent.change(reasonBox(), {
      target: { value: '  Committed to our own hand-over in July.  ' },
    });
    expect(refuseButton()).toBeEnabled();

    fireEvent.click(refuseButton());

    await waitFor(() =>
      expect(onRefuse).toHaveBeenCalledWith('Committed to our own hand-over in July.'),
    );
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it('leaves the claim alone when the refusal is cancelled', () => {
    renderDialog();

    fireEvent.change(reasonBox(), { target: { value: 'Committed elsewhere.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onDone).toHaveBeenCalled();
    expect(onRefuse).not.toHaveBeenCalled();
  });

  it('blocks a second refusal while the first is in flight', () => {
    renderDialog({ submitting: true });

    fireEvent.change(reasonBox(), { target: { value: 'Committed elsewhere.' } });

    expect(refuseButton()).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });
});
