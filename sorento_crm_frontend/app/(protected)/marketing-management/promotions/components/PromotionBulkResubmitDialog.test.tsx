/**
 * Tests for the promotion bulk-resubmit confirmation.
 *
 * The eligibility split is the safety-critical part: re-extraction rebuilds a
 * promotion from ONE flyer's payload, dropping every existing group and attachment
 * link first. Sending a two-flyer promotion through it would unlink the second flyer,
 * so those rows must be skipped and said out loud rather than quietly included.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const mutate = vi.fn();
vi.mock('../hooks/usePromotions', () => ({
  useResubmitPromotionFlyers: () => ({ mutate, isPending: false }),
}));

import PromotionBulkResubmitDialog, {
  splitPromotionsForResubmit,
} from './PromotionBulkResubmitDialog';
import type { Promotion } from '../types/promotion.types';

function promotion(id: string, attachmentIds: string[]): Promotion {
  return {
    id,
    description: `Promo ${id}`,
    attachments: attachmentIds.map((attachment_id, i) => ({
      id: `link-${attachment_id}`,
      attachment_id,
      sort_order: i,
    })),
  } as unknown as Promotion;
}

describe('splitPromotionsForResubmit', () => {
  it('treats a single-flyer promotion as eligible', () => {
    const split = splitPromotionsForResubmit([promotion('p1', ['a1'])]);
    expect(split.eligible.map((p) => p.id)).toEqual(['p1']);
    expect(split.noAttachment).toHaveLength(0);
    expect(split.multiAttachment).toHaveLength(0);
  });

  it('excludes a promotion with no flyer - there is nothing to re-extract', () => {
    const split = splitPromotionsForResubmit([promotion('p1', [])]);
    expect(split.eligible).toHaveLength(0);
    expect(split.noAttachment.map((p) => p.id)).toEqual(['p1']);
  });

  it('excludes a multi-flyer promotion - re-extracting one unlinks the others', () => {
    const split = splitPromotionsForResubmit([promotion('p1', ['a1', 'a2'])]);
    expect(split.eligible).toHaveLength(0);
    expect(split.multiAttachment.map((p) => p.id)).toEqual(['p1']);
  });

  it('tolerates a row whose attachments field is absent entirely', () => {
    const bare = { id: 'p1', description: 'no attachments key' } as unknown as Promotion;
    expect(() => splitPromotionsForResubmit([bare])).not.toThrow();
    expect(splitPromotionsForResubmit([bare]).noAttachment).toHaveLength(1);
  });
});

describe('PromotionBulkResubmitDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  const noop = () => {};

  it('submits only the eligible promotions flyer ids', () => {
    render(
      <PromotionBulkResubmitDialog
        open
        onOpenChange={noop}
        promotions={[
          promotion('p1', ['a1']),
          promotion('p2', []),
          promotion('p3', ['a3', 'a4']),
          promotion('p4', ['a5']),
        ]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /^Resubmit 2$/ }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual(['a1', 'a5']);
  });

  it('says how many rows are skipped and why', () => {
    render(
      <PromotionBulkResubmitDialog
        open
        onOpenChange={noop}
        promotions={[promotion('p1', ['a1']), promotion('p2', []), promotion('p3', ['a3', 'a4'])]}
      />,
    );

    expect(screen.getByText(/Skipping 1 promotion with no flyer attached/)).toBeTruthy();
    expect(
      screen.getByText(/Skipping 1 promotion with more than one flyer/),
    ).toBeTruthy();
  });

  it('warns that the existing products are replaced', () => {
    render(
      <PromotionBulkResubmitDialog open onOpenChange={noop} promotions={[promotion('p1', ['a1'])]} />,
    );
    expect(screen.getByText(/Existing groups and products are replaced/)).toBeTruthy();
    expect(screen.getByText(/cannot be undone/)).toBeTruthy();
  });

  it('stays open when every flyer failed, so the selection can be retried', () => {
    // The mutation tallies rather than throws, so a total failure still lands in
    // onSuccess - the dialog must not treat that as done.
    mutate.mockImplementation((_ids: string[], opts: { onSuccess: (r: unknown) => void }) =>
      opts.onSuccess({ succeeded: 0, failures: ['n8n unreachable'] }),
    );
    const onOpenChange = vi.fn();
    const onSuccessSpy = vi.fn();

    render(
      <PromotionBulkResubmitDialog
        open
        onOpenChange={onOpenChange}
        promotions={[promotion('p1', ['a1'])]}
        onSuccess={onSuccessSpy}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /^Resubmit 1$/ }));

    expect(onOpenChange).not.toHaveBeenCalled();
    expect(onSuccessSpy).not.toHaveBeenCalled();
  });

  it('closes and clears the selection once at least one flyer went through', () => {
    mutate.mockImplementation((_ids: string[], opts: { onSuccess: (r: unknown) => void }) =>
      opts.onSuccess({ succeeded: 1, failures: [] }),
    );
    const onOpenChange = vi.fn();
    const onSuccessSpy = vi.fn();

    render(
      <PromotionBulkResubmitDialog
        open
        onOpenChange={onOpenChange}
        promotions={[promotion('p1', ['a1'])]}
        onSuccess={onSuccessSpy}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /^Resubmit 1$/ }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onSuccessSpy).toHaveBeenCalled();
  });

  it('disables confirm when nothing selected is eligible', () => {
    render(
      <PromotionBulkResubmitDialog
        open
        onOpenChange={noop}
        promotions={[promotion('p1', []), promotion('p2', ['a1', 'a2'])]}
      />,
    );
    const confirm = screen.getByRole('button', { name: /^Resubmit 0$/ });
    expect(confirm.hasAttribute('disabled')).toBe(true);
    fireEvent.click(confirm);
    expect(mutate).not.toHaveBeenCalled();
  });
});
