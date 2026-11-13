/** NON-CANCELLABLE-ITEMS: reading the refusal from a Confirm all result and from an HTTP 409. */
import { describe, expect, it } from 'vitest';
import {
  NonCancellableRefusalError,
  overridableRefusalOf,
  refusalAwareError,
} from './nonCancellable';

const LINES = [{ label: 'Bathtub X', from_qty: 5, to_qty: 3 }];

describe('overridableRefusalOf', () => {
  it('merges the lines of every overridable refused order', () => {
    const refusal = overridableRefusalOf([
      { ok: true },
      {
        ok: false,
        error_code: 'non_cancellable_line',
        error_details: { can_override: true, lines: LINES },
      },
      {
        ok: false,
        error_code: 'non_cancellable_line',
        error_details: { can_override: true, lines: [{ label: 'Tub Y', from_qty: 2, to_qty: 0 }] },
      },
    ]);
    expect(refusal?.lines.map((line) => line.label)).toEqual(['Bathtub X', 'Tub Y']);
  });

  it('is null when the refusal cannot be overridden or is another error', () => {
    expect(
      overridableRefusalOf([
        {
          ok: false,
          error_code: 'non_cancellable_line',
          error_details: { can_override: false, lines: LINES },
        },
        { ok: false, error_code: 'other' },
      ]),
    ).toBeNull();
  });
});

describe('refusalAwareError', () => {
  it('turns a 409 non_cancellable_line into a refusal carrying its details', async () => {
    const response = new Response(
      JSON.stringify({
        code: 'non_cancellable_line',
        message: 'Non-cancellable: Bathtub X',
        detail: 'Non-cancellable: Bathtub X',
        details: { can_override: true, lines: LINES },
      }),
      { status: 409, headers: { 'content-type': 'application/json' } },
    );
    const error = await refusalAwareError(response, 'fallback');
    expect(error).toBeInstanceOf(NonCancellableRefusalError);
    expect((error as NonCancellableRefusalError).details.lines).toEqual(LINES);
  });

  it('keeps a plain Error for anything else', async () => {
    const response = new Response(JSON.stringify({ detail: 'nope' }), {
      status: 409,
      headers: { 'content-type': 'application/json' },
    });
    const error = await refusalAwareError(response, 'fallback');
    expect(error).not.toBeInstanceOf(NonCancellableRefusalError);
    expect(error.message).toBe('nope');
  });
});
