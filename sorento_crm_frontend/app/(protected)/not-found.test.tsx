/**
 * M5-04 - the route-level 404 for everything under `app/(protected)`. Same
 * split as `error.test.tsx`: content here, shell survival in the browser run.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import ProtectedNotFound from './not-found';

describe('app/(protected)/not-found.tsx (M5-04)', () => {
  it('states the record is gone and offers a link back', () => {
    render(<ProtectedNotFound />);

    expect(screen.getByText('This record does not exist or was removed.')).toBeInTheDocument();

    const link = screen.getByRole('link', { name: /back to dashboards/i });
    expect(link).toHaveAttribute('href', '/');
  });
});
