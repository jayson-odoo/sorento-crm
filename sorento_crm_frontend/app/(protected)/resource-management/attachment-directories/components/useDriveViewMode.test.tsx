/**
 * useDriveViewMode — list/grid persistence per user (UAC A5).
 */
import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

import { useDriveViewMode } from './useDriveViewMode';

const STORAGE_KEY = 'resource-management.drive.view-mode';

function Harness() {
  const [mode, setMode] = useDriveViewMode();
  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <button onClick={() => setMode('grid')}>to-grid</button>
      <button onClick={() => setMode('list')}>to-list</button>
    </div>
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

describe('useDriveViewMode', () => {
  it('defaults to list (D12) when nothing is stored', () => {
    render(<Harness />);
    expect(screen.getByTestId('mode').textContent).toBe('list');
  });

  it('persists the chosen mode to localStorage', () => {
    render(<Harness />);
    act(() => {
      fireEvent.click(screen.getByText('to-grid'));
    });
    expect(screen.getByTestId('mode').textContent).toBe('grid');
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('grid');
  });

  it('hydrates from localStorage on mount (survives reload)', () => {
    window.localStorage.setItem(STORAGE_KEY, 'grid');
    render(<Harness />);
    // effect runs synchronously under RTL act() — mode hydrates to grid.
    expect(screen.getByTestId('mode').textContent).toBe('grid');
  });
});
