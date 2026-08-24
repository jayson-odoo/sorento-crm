/**
 * AccessLevelsCell - single-line access badges + "+N" overflow popover (review A).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import AccessLevelsCell from './AccessLevelsCell';

const nameByCode = new Map<string, string>([
  ['public', 'Public'],
  ['internal', 'Internal'],
  ['finance', 'Finance'],
  ['legal', 'Legal'],
]);

beforeEach(() => {
  // Radix Popover reads matchMedia / ResizeObserver in jsdom.
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
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
});
afterEach(() => vi.unstubAllGlobals());

describe('AccessLevelsCell', () => {
  it('renders a dash when there are no access levels', () => {
    render(<AccessLevelsCell levels={[]} nameByCode={nameByCode} />);
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('shows up to 2 badges inline and no "+N" chip when 2 or fewer', () => {
    render(<AccessLevelsCell levels={['public', 'internal']} nameByCode={nameByCode} />);
    expect(screen.getByText('Public')).toBeInTheDocument();
    expect(screen.getByText('Internal')).toBeInTheDocument();
    expect(screen.queryByText(/^\+\d+$/)).not.toBeInTheDocument();
  });

  it('collapses overflow into a "+N" chip (single row) and resolves codes to names', () => {
    render(
      <AccessLevelsCell levels={['public', 'internal', 'finance', 'legal']} nameByCode={nameByCode} />
    );
    // Only the first 2 render inline; the rest hide behind the chip.
    expect(screen.getByText('Public')).toBeInTheDocument();
    expect(screen.getByText('Internal')).toBeInTheDocument();
    expect(screen.getByText('+2')).toBeInTheDocument();
    // Overflow members are NOT visible inline before the popover opens.
    expect(screen.queryByText('Finance')).not.toBeInTheDocument();
    expect(screen.queryByText('Legal')).not.toBeInTheDocument();
  });

  it('"+N" opens a popover listing ALL access levels', () => {
    render(
      <AccessLevelsCell levels={['public', 'internal', 'finance', 'legal']} nameByCode={nameByCode} />
    );
    fireEvent.click(screen.getByText('+2'));
    const popover = screen.getByText('Access levels').closest('[data-slot]') as HTMLElement;
    const scope = within(popover ?? document.body);
    // All four levels appear inside the popover.
    expect(scope.getAllByText('Public').length).toBeGreaterThanOrEqual(1);
    expect(scope.getByText('Finance')).toBeInTheDocument();
    expect(scope.getByText('Legal')).toBeInTheDocument();
  });

  it('falls back to the raw code when no friendly name is mapped', () => {
    render(<AccessLevelsCell levels={['unknown_code']} nameByCode={nameByCode} />);
    expect(screen.getByText('unknown_code')).toBeInTheDocument();
  });
});
