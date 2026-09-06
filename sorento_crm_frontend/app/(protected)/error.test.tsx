/**
 * M5-04 - the route-level error boundary for everything under
 * `app/(protected)`. This test proves the CONTENT: fixed copy (never the raw
 * `error.message` - M5-04 review B2), the digest shown when present, Try
 * again calls `reset`, a link home exists. Whether the shell (sidebar,
 * header) survives around it is Next's own file-convention behaviour - an
 * `error.tsx` mounts INSIDE its segment's `layout.tsx`, replacing only the
 * `children` slot - and is verified in the browser (M5-04's `[browser]`
 * half), not re-asserted here.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import ProtectedError from './error';

describe('app/(protected)/error.tsx (M5-04)', () => {
  it('shows fixed copy plus the digest, never the raw error message, and Try again calls reset', () => {
    const reset = vi.fn();
    const error = Object.assign(new Error('Something exploded'), { digest: 'abc123' });

    render(<ProtectedError error={error} reset={reset} />);

    expect(screen.getByText('Something went wrong on this page.')).toBeInTheDocument();
    expect(screen.getByText('Reference: abc123')).toBeInTheDocument();
    // Never the raw message - a server-component throw's boilerplate, a client
    // throw's generic text, or a rethrown API message can all carry a record id.
    expect(screen.queryByText('Something exploded')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it('omits the reference line when there is no digest', () => {
    render(<ProtectedError error={new Error('x')} reset={vi.fn()} />);

    expect(screen.getByText('Something went wrong on this page.')).toBeInTheDocument();
    expect(screen.queryByText(/^Reference:/)).not.toBeInTheDocument();
  });

  it('offers a link back to dashboards', () => {
    render(<ProtectedError error={new Error('x')} reset={vi.fn()} />);

    const link = screen.getByRole('link', { name: /back to dashboards/i });
    expect(link).toHaveAttribute('href', '/');
  });
});
