/**
 * What can be done to a price tag request right now (r9 AC-S2-7, AC-S3-4/5/6).
 *
 * The FIRST entry is the page's one primary CTA and everything after it lives
 * in the gear, so the whole "one loud button, the rest in the dropdown" rule is
 * a property of this list. r9 gives it two new inputs and both of them change
 * the ANSWER, not just the label:
 *
 * * the open change-request count rides on `Mark design ready` (D6) and never
 *   blocks it (D2) - somebody who has decided a comment does not apply must
 *   still be able to send the design back;
 * * `print_by` decides what `approved` means (D7/D8). Self print ends there;
 *   office print starts the hand-over there; a row from before the choice
 *   existed offers neither rather than guessing.
 */
import { describe, it, expect } from 'vitest';

import { priceTagActions } from './priceTagRequestActions';

const labels = (...args: Parameters<typeof priceTagActions>) =>
  priceTagActions(...args).map((action) => action.label);
const kinds = (...args: Parameters<typeof priceTagActions>) =>
  priceTagActions(...args).map((action) => action.action);

describe('the open change-request count (AC-S2-7)', () => {
  it('rides on the Mark design ready label', () => {
    expect(labels('changes_requested', 'user-1', 2)).toContain(
      'Mark design ready (2 open)',
    );
  });

  it('says nothing extra when there is nothing open', () => {
    expect(labels('designing', 'user-1', 0)).toContain('Mark design ready');
    expect(labels('designing', 'user-1', 0)).not.toContain('Mark design ready (0 open)');
  });

  it('never blocks the transition (D2)', () => {
    expect(kinds('designing', 'user-1', 5)).toContain('mark_proof_ready');
  });
});

describe('approved, by who prints (AC-S3-4, AC-S3-5)', () => {
  it('a self print is finished: Export PDF and nothing else', () => {
    expect(kinds('approved', 'user-1', 0, 'self')).toEqual(['export']);
  });

  it('an office print leads with Mark ready for collection', () => {
    const actions = priceTagActions('approved', 'user-1', 0, 'office');

    expect(actions[0]).toMatchObject({
      action: 'mark_ready_for_collection',
      label: 'Mark ready for collection',
    });
    expect(actions.map((action) => action.action)).toContain('export');
  });

  it('a row with no print choice offers neither hand-over step', () => {
    const actions = kinds('approved', 'user-1', 0, null);

    expect(actions).not.toContain('mark_ready_for_collection');
    expect(actions).not.toContain('mark_collected');
    expect(actions).toContain('export');
  });
});

describe('the hand-over (AC-S3-6)', () => {
  it('ready_for_collection leads with Mark collected', () => {
    const actions = priceTagActions('ready_for_collection', 'user-1', 0, 'office');

    expect(actions[0]).toMatchObject({
      action: 'mark_collected',
      label: 'Mark collected',
    });
  });

  it('a request waiting to be collected cannot be voided out from under it', () => {
    expect(kinds('ready_for_collection', 'user-1', 0, 'office')).not.toContain('void');
  });

  it('collected is the end of the list', () => {
    expect(kinds('collected', 'user-1', 0, 'office')).toEqual(['export']);
  });
});

describe('`ready` is gone (AC-S3-3)', () => {
  it('offers nothing that names it', () => {
    expect(labels('ready', 'user-1', 0, 'office')).not.toContain('Export PDF');
  });
});

describe('the rest of the lifecycle is unchanged', () => {
  it.each([
    ['new', null, 'Claim'],
    ['new', 'user-1', 'Design tags'],
    ['designing', 'user-1', 'Design tags'],
    ['changes_requested', 'user-1', 'Design tags'],
    ['proof_ready', 'user-1', 'View design'],
  ])('%s is led by %s', (status, assignee, label) => {
    expect(priceTagActions(status, assignee)[0].label).toBe(label);
  });

  it.each(['rejected', 'void'])('%s offers nothing at all', (status) => {
    expect(priceTagActions(status, 'user-1')).toEqual([]);
  });

  it('Void is marked destructive wherever it is still legal', () => {
    const voidAction = priceTagActions('designing', 'user-1').find(
      (action) => action.action === 'void',
    );
    expect(voidAction?.destructive).toBe(true);
  });
});
