/**
 * TOGGLE-SELECTED - the List | Board switch shows its selected view in the primary colour.
 * It used to override the shared selected fill with `bg-background` (white), which after the
 * shared fix would also have left a white icon on a white segment.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ListBoardViewToggle } from './ListBoardViewToggle';

describe('ListBoardViewToggle', () => {
  it('the selected view is primary, the other is not on', () => {
    render(<ListBoardViewToggle value="board" onChange={vi.fn()} />);
    const board = screen.getByRole('radio', { name: 'Board view' });
    expect(board.getAttribute('data-state')).toBe('on');
    const cls = board.getAttribute('class') ?? '';
    expect(cls).toContain('data-[state=on]:bg-primary');
    expect(cls).toContain('data-[state=on]:text-primary-foreground');
    expect(cls).not.toContain('data-[state=on]:bg-background');
    expect(screen.getByRole('radio', { name: 'List view' }).getAttribute('data-state')).toBe('off');
  });
});
