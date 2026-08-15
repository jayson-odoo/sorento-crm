/**
 * WallPicker - the opening editor's "which wall" round-trip.
 *
 * Extracted out of `RoomDesigner` (see its file header) because that
 * component wraps a raw three.js canvas that jsdom cannot mount. This pins
 * the two things `RoomDesigner` relies on: the wall index goes IN as
 * `String(wallIndex)` and comes back OUT as `Number(value)` - a regression
 * here (e.g. forgetting the `Number()` conversion) would hand `moveOpening`
 * a string wallIndex and silently break wall reassignment.
 *
 * SearchableSelect is stubbed to a native <select> - the established pattern
 * for deterministic dropdowns under jsdom (see CertificatesList.test.tsx).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
  }: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
  }) => (
    <select id={id} aria-label="Wall" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { WallPicker } from './WallPicker';

describe('WallPicker', () => {
  it('labels each wall with its 1-based number and rounded length in mm', () => {
    render(
      <WallPicker id="dk-opening-wall" walls={[4000, 3000.4, 2500.6]} value={0} onChange={vi.fn()} />,
    );
    expect(screen.getByRole('option', { name: '1 (4000 mm)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '2 (3000 mm)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '3 (2501 mm)' })).toBeInTheDocument();
  });

  it('reflects the selected wallIndex as the current value', () => {
    render(<WallPicker walls={[4000, 3000, 2500]} value={2} onChange={vi.fn()} />);
    expect((screen.getByLabelText('Wall') as HTMLSelectElement).value).toBe('2');
  });

  it('choosing a different wall calls onChange with a NUMBER, not a string', () => {
    const onChange = vi.fn();
    render(<WallPicker walls={[4000, 3000, 2500]} value={0} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText('Wall'), { target: { value: '2' } });

    expect(onChange).toHaveBeenCalledWith(2);
    expect(onChange).not.toHaveBeenCalledWith('2');
  });
});
