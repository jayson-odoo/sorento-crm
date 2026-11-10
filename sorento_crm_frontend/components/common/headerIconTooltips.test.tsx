/**
 * UIUX-QUICK-WINS item 9: the detail header's icon buttons (gear, previous, next) carry the
 * shared styled Tooltip as their visible label, not the browser's native `title`.
 */
import React from 'react';
import { describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';

import { DetailActionsMenu } from './DetailActionsMenu';
import RecordNavigation from './RecordNavigation';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';

async function tooltipFor(button: HTMLElement) {
  await act(async () => {
    fireEvent.focus(button);
  });
  return screen.findByRole('tooltip');
}

describe('header icon buttons use the shared Tooltip', () => {
  it('the gear names itself in a tooltip and has no native title', async () => {
    render(
      <DetailActionsMenu>
        <DropdownMenuItem>Export</DropdownMenuItem>
      </DetailActionsMenu>,
    );
    const gear = screen.getByRole('button', { name: 'Actions' });
    expect(gear).not.toHaveAttribute('title');
    expect(await tooltipFor(gear)).toHaveTextContent('Actions');
  });

  it('previous and next name themselves in a tooltip', async () => {
    render(
      <RecordNavigation
        ariaLabel="order inquiry"
        hasPrevious
        hasNext
        onPrevious={() => {}}
        onNext={() => {}}
        index={2}
        total={5}
      />,
    );
    expect(await tooltipFor(screen.getByRole('button', { name: 'Previous order inquiry' }))).toHaveTextContent(
      'Previous order inquiry',
    );
  });
});
