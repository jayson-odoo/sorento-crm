/**
 * DATE-PICKER-UNIFY: `portal` renders the range calendar at the document root, so a Dialog's
 * overflow box cannot clip it (same prop DatePicker already has). Without it the calendar
 * stays in place.
 */
import * as React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DateRangePicker } from './date-range-picker';

function setup(portal: boolean) {
  const { container } = render(
    <div data-testid="box">
      {/* `portal` is the prop under test */}
      <DateRangePicker from="2026-11-01" to="2026-11-30" onChange={() => {}} portal={portal} />
    </div>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Pick a date range' }));
  return { container, box: screen.getByTestId('box') };
}

describe('DateRangePicker portal', () => {
  it('with portal the calendar grid is NOT inside the container', async () => {
    const { box } = setup(true);
    const grid = await screen.findByRole('grid');
    expect(box.contains(grid)).toBe(false);
    expect(document.body.contains(grid)).toBe(true);
  });

  it('control: without portal the calendar grid stays inside the container', async () => {
    const { box } = setup(false);
    const grid = await screen.findByRole('grid');
    expect(box.contains(grid)).toBe(true);
  });
});
