/**
 * Fix lane round 2 (reviewer Nit 1 on PR #1307): after an error the phone
 * step clears the box, and retyping the SAME code must fire `onComplete`
 * again. Before the fix the last-fired guard kept the old code, so after a
 * network blip the right code never re-submitted and there is no button.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import { OtpCodeField } from './OtpCodeField';

function field(value: string, onComplete: (code: string) => void) {
  return (
    <OtpCodeField
      value={value}
      onChange={() => {}}
      onComplete={onComplete}
      cooldown={0}
      sent
      pending={false}
      onResend={() => {}}
    />
  );
}

describe('OtpCodeField auto-submit guard', () => {
  it('fires once per distinct value while it stays in the box', () => {
    const onComplete = vi.fn();
    const { rerender } = render(field('123456', onComplete));
    rerender(field('123456', onComplete));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('fires again for the same code once the box has been cleared', () => {
    const onComplete = vi.fn();
    const { rerender } = render(field('123456', onComplete));
    rerender(field('', onComplete));
    rerender(field('123456', onComplete));
    expect(onComplete).toHaveBeenCalledTimes(2);
    expect(onComplete).toHaveBeenLastCalledWith('123456');
  });
});
