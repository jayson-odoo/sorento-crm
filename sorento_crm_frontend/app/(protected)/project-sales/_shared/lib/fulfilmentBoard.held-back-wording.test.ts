/**
 * BORROW-CONFIRM-MATCH (owner, 22 Oct 2026, prod SO401624): the press printed "was confirmed, but
 * its staged rejection could not ride along with the pending change" beside the server's own "1
 * line cannot be confirmed. Nothing was written." The held-back note is built before the server
 * answers, so its wording is settled once the answers are in: "was confirmed" only when that same
 * order came back ok.
 */
import { describe, expect, it } from 'vitest';
import {
  HELD_BACK_ALONE,
  HELD_BACK_BESIDE_CONFIRM,
  settleHeldBackNotes,
} from './fulfilmentBoard';

const PSO = 'pso-401624';

type Entry = {
  pso_id: string;
  so_number?: string;
  ok: boolean;
  heldBack?: boolean;
  error?: string | null;
};

const settle = (entries: Entry[]) => settleHeldBackNotes(entries);

const note: Entry = {
  pso_id: PSO,
  so_number: 'SO401624',
  ok: false,
  heldBack: true,
  error: HELD_BACK_BESIDE_CONFIRM,
};

describe('settleHeldBackNotes', () => {
  it('drops "was confirmed" when the server refused the whole order', () => {
    const refused = {
      pso_id: PSO,
      ok: false,
      error: '1 line cannot be confirmed. Nothing was written.',
    };
    const [settled, server] = settle([note, refused]);
    expect(settled.error).toBe(HELD_BACK_ALONE);
    expect(settled.error).not.toContain('was confirmed');
    expect(server).toBe(refused);
  });

  it('keeps "was confirmed" when the same order came back ok', () => {
    const [settled] = settle([note, { pso_id: PSO, ok: true }]);
    expect(settled.error).toBe(HELD_BACK_BESIDE_CONFIRM);
  });

  it('drops it when the order was never posted (dry run left nothing to confirm)', () => {
    const nothing = {
      pso_id: PSO,
      ok: false,
      heldBack: true,
      error: 'has nothing to confirm',
    };
    const [settled] = settle([note, nothing]);
    expect(settled.error).toBe(HELD_BACK_ALONE);
  });

  it("does not take another order's success as this order's", () => {
    const [settled] = settle([note, { pso_id: 'pso-other', ok: true }]);
    expect(settled.error).toBe(HELD_BACK_ALONE);
  });
});
