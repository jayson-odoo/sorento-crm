/**
 * UI v2 phase 0, slice S3 (red first). UAC B-12.
 *
 * EXPORT CONTRACT:
 *   components/v2/version/Versioned.tsx : Versioned({ v1, v2 }: { v1: ReactNode; v2: ReactNode })
 *     Renders exactly one side by useUiVersion().uiVersion. It reads context only: no fetch of its own
 *     (it must not call apiFetch / fetch) and no QueryClientProvider is needed to render it.
 *   components/v2/version/useUiVersion.ts is the context hook (see UiVersionProvider.test.tsx).
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

const state = { uiVersion: 'v1' as 'v1' | 'v2', uiV2Available: true, isLoading: false, setUiVersion: vi.fn() };
vi.mock('./useUiVersion', () => ({ useUiVersion: () => state }));

import { Versioned } from './Versioned';

const fetchSpy = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('fetch', fetchSpy);
  state.uiVersion = 'v1';
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('Versioned', () => {
  it('renders only the v1 side in v1', () => {
    render(<Versioned v1={<p>old screen</p>} v2={<p>new screen</p>} />);
    expect(screen.getByText('old screen')).toBeInTheDocument();
    expect(screen.queryByText('new screen')).toBeNull();
  });

  it('renders only the v2 side in v2', () => {
    state.uiVersion = 'v2';
    render(<Versioned v1={<p>old screen</p>} v2={<p>new screen</p>} />);
    expect(screen.getByText('new screen')).toBeInTheDocument();
    expect(screen.queryByText('old screen')).toBeNull();
  });

  it('reads the version from context only: no request', () => {
    state.uiVersion = 'v2';
    render(<Versioned v1={<p>a</p>} v2={<p>b</p>} />);
    expect(apiFetch).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
