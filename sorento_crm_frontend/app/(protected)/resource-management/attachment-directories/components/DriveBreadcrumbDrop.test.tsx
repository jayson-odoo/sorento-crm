/**
 * DriveBreadcrumb drop-target highlight (review E). A crumb hovered by a drag
 * must highlight strongly so it's clear which ancestor will receive the drop.
 * jsdom can't run a real dnd-kit drag, so useDroppable is mocked to isOver:true.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@dnd-kit/core', async () => {
  const actual = await vi.importActual<typeof import('@dnd-kit/core')>('@dnd-kit/core');
  return {
    ...actual,
    useDroppable: () => ({ setNodeRef: vi.fn(), isOver: true }),
  };
});

import DriveBreadcrumb from './DriveBreadcrumb';
import { DndContext } from '@dnd-kit/core';

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

describe('DriveBreadcrumb drop highlight', () => {
  it('a crumb hovered by a drag gets a strong ring + bg highlight', () => {
    render(
      <DndContext>
        <DriveBreadcrumb
          crumbs={[
            { id: null, name: 'All files' },
            { id: 'mkt', name: 'Marketing' },
          ]}
          onNavigate={vi.fn()}
        />
      </DndContext>
    );
    const crumb = screen.getByText('Marketing').closest('button') as HTMLElement;
    expect(crumb.className).toContain('ring-primary');
    expect(crumb.className).toContain('bg-primary/10');
  });
});
