import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/hooks/useTownSnapshot', () => ({
  useTownSnapshot: () => ({ snapshot: undefined, error: null, isLoading: true }),
}));
vi.mock('next/dynamic', () => ({ default: () => () => null }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/town',
  useSearchParams: () => new URLSearchParams(),
}));

import { TownPage } from './TownPage';

describe('TownPage while the first fetch runs', () => {
  it('shows a loading status and no cards', () => {
    render(<TownPage />);
    expect(screen.getByRole('status', { name: /loading town/i })).toBeTruthy();
    expect(screen.queryByText('How much did we sell today?')).toBeNull();
  });
});
