/** AC-PS-16: the three new rungs are coloured, not the neutral fallback. */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ProjectStatusPill } from './ProjectStatusPill';

function pillClass(statusKey: string, label: string) {
  const { unmount } = render(<ProjectStatusPill statusKey={statusKey} label={label} />);
  const cls = screen.getByText(label).className;
  unmount();
  return cls;
}

describe('ProjectStatusPill ladder rungs (AC-PS-16)', () => {
  const fallback = pillClass('zz_unmapped_rung', 'Unmapped');

  it.each([
    ['sample_submission', 'Sample Submission'],
    ['final_negotiation', 'Final Negotiation'],
    ['sponsorship_form', 'Sponsorship Form'],
  ])('%s is not the neutral fallback', (key, label) => {
    expect(pillClass(key, label)).not.toBe(fallback);
  });
});
