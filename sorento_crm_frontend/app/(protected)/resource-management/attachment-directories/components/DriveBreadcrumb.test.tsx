/**
 * DriveBreadcrumb - path trail + crumb navigation (UAC A2).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DndContext } from '@dnd-kit/core';

import DriveBreadcrumb from './DriveBreadcrumb';

beforeEach(() => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((q: string) => ({
      matches: false,
      media: q,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  );
});
afterEach(() => vi.unstubAllGlobals());

const crumbs = [
  { id: null, name: 'All files' },
  { id: 'mkt', name: 'Marketing' },
  { id: 'camp', name: 'Campaigns' },
];

describe('DriveBreadcrumb', () => {
  it('A2: renders every crumb in order', () => {
    render(
      <DndContext>
        <DriveBreadcrumb crumbs={crumbs} onNavigate={vi.fn()} />
      </DndContext>
    );
    expect(screen.getByText('All files')).toBeInTheDocument();
    expect(screen.getByText('Marketing')).toBeInTheDocument();
    expect(screen.getByText('Campaigns')).toBeInTheDocument();
  });

  it('A2: clicking an ancestor crumb navigates to it', () => {
    const onNavigate = vi.fn();
    render(
      <DndContext>
        <DriveBreadcrumb crumbs={crumbs} onNavigate={onNavigate} />
      </DndContext>
    );
    fireEvent.click(screen.getByText('Marketing'));
    expect(onNavigate).toHaveBeenCalledWith('mkt');
  });

  it('A2: clicking the root crumb navigates to null (root)', () => {
    const onNavigate = vi.fn();
    render(
      <DndContext>
        <DriveBreadcrumb crumbs={crumbs} onNavigate={onNavigate} />
      </DndContext>
    );
    fireEvent.click(screen.getByText('All files'));
    expect(onNavigate).toHaveBeenCalledWith(null);
  });
});
