/**
 * UI v2 phase 0, slice S3 (red first). UAC B-10.
 *
 * EXPORT CONTRACT:
 *   components/v2/version/PreviousVersionChip.tsx : PreviousVersionChip()
 *     The small marker shown on a route that has no v2 client yet, inside the v2 shell. Text "Previous-version
 *     screen". Renders only when useUiVersion().uiV2Available is true (the owner-only cohort); renders nothing
 *     for everyone else. Reads context only.
 */
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

const state = { uiVersion: 'v2' as 'v1' | 'v2', uiV2Available: true, isLoading: false, setUiVersion: vi.fn() };
vi.mock('./useUiVersion', () => ({ useUiVersion: () => state }));

import { PreviousVersionChip } from './PreviousVersionChip';

afterEach(() => {
  cleanup();
  state.uiVersion = 'v2';
  state.uiV2Available = true;
});

describe('PreviousVersionChip', () => {
  it('shows for a user with v2 available', () => {
    render(<PreviousVersionChip />);
    expect(screen.getByText('Previous-version screen')).toBeInTheDocument();
  });

  it('renders nothing when v2 is not available to the user', () => {
    state.uiV2Available = false;
    const { container } = render(<PreviousVersionChip />);
    expect(screen.queryByText('Previous-version screen')).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });
});
