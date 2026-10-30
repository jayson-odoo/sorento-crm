/**
 * AllowedItemClassesPicker (TAG-BRAND-CLASS AC-6 / AC-7): the shared "Allowed item classes"
 * block under Brands, on the contact card and the tag Access settings.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import AllowedItemClassesPicker, { NO_CLASS, nextAllowedClasses } from './AllowedItemClassesPicker';

afterEach(() => cleanup());

const OPTIONS = [
  { value: NO_CLASS, label: 'No class' },
  { value: 'DIY', label: 'SORENTO LITE - DIY' },
  { value: 'SERENE', label: 'SORENTO SERENE SERIES' },
];

describe('nextAllowedClasses', () => {
  it('ticks No class with the first class picked into an empty list', () => {
    expect(nextAllowedClasses([], ['DIY'])).toEqual([NO_CLASS, 'DIY']);
  });

  it('lets No class be unticked afterwards', () => {
    expect(nextAllowedClasses([NO_CLASS, 'DIY'], ['DIY'])).toEqual(['DIY']);
  });

  it('does not add No class twice, and clearing gives every class', () => {
    expect(nextAllowedClasses([], [NO_CLASS])).toEqual([NO_CLASS]);
    expect(nextAllowedClasses([NO_CLASS, 'DIY'], [])).toEqual([]);
  });

  it('a later pick never re-adds No class', () => {
    expect(nextAllowedClasses(['DIY'], ['DIY', 'SERENE'])).toEqual(['DIY', 'SERENE']);
  });
});

describe('AllowedItemClassesPicker read-only', () => {
  it('shows "All classes" when nothing is allowed', () => {
    render(<AllowedItemClassesPicker id="x" value={[]} onChange={() => {}} options={OPTIONS} editing={false} />);
    expect(screen.getByText('Allowed item classes')).toBeInTheDocument();
    expect(screen.getByText('All classes')).toBeInTheDocument();
  });

  it('shows names for known codes and the code itself for a retired one', () => {
    render(
      <AllowedItemClassesPicker
        id="x"
        value={[NO_CLASS, 'DIY', 'OLDCLASS']}
        onChange={() => {}}
        options={OPTIONS}
        editing={false}
      />,
    );
    expect(screen.getByText('No class')).toBeInTheDocument();
    expect(screen.getByText('SORENTO LITE - DIY')).toBeInTheDocument();
    expect(screen.getByText('OLDCLASS')).toBeInTheDocument();
    expect(screen.queryByText('SORENTO SERENE SERIES')).toBeNull();
  });
});
