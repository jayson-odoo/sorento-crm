/**
 * DriveImageThumbnail — lazy image card (UAC G1/G3).
 *
 * Asserts: NO preview-url fetch and NO <img src> until the card intersects the
 * viewport; once it does, the resolved serve URL is set as the src.
 *
 * jsdom has no IntersectionObserver, so we install a controllable fake that lets
 * the test decide when the element "enters" the viewport.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';

import DriveImageThumbnail from './DriveImageThumbnail';
import { getAttachmentPreviewUrl } from '../../attachments/services/attachmentService';

vi.mock('../../attachments/services/attachmentService', () => ({
  getAttachmentPreviewUrl: vi.fn(),
}));
const mockedPreview = vi.mocked(getAttachmentPreviewUrl);

type IOCallback = (entries: { isIntersecting: boolean }[]) => void;
let lastCallback: IOCallback | null = null;

class FakeIntersectionObserver {
  constructor(cb: IOCallback) {
    lastCallback = cb;
  }
  observe() {}
  disconnect() {}
  unobserve() {}
}

beforeEach(() => {
  mockedPreview.mockReset();
  mockedPreview.mockResolvedValue('https://cdn.example/serve/abc.png');
  lastCallback = null;
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver as unknown as typeof IntersectionObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DriveImageThumbnail', () => {
  it('G3: does NOT fetch the preview URL while off-screen', () => {
    render(<DriveImageThumbnail attachmentId="a1" alt="photo" />);
    // The IO callback has not fired -> not in view -> no fetch, no <img>.
    expect(mockedPreview).not.toHaveBeenCalled();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('G1: fetches the serve URL and renders a lazy <img> once it scrolls into view', async () => {
    render(<DriveImageThumbnail attachmentId="a1" alt="photo" />);
    expect(mockedPreview).not.toHaveBeenCalled();

    // Simulate the card entering the viewport.
    await act(async () => {
      lastCallback?.([{ isIntersecting: true }]);
    });

    await waitFor(() => expect(mockedPreview).toHaveBeenCalledWith('a1'));
    const img = await screen.findByRole('img');
    expect(img).toHaveAttribute('src', 'https://cdn.example/serve/abc.png');
    expect(img).toHaveAttribute('loading', 'lazy');
  });

  it('G2: shows the icon fallback (no broken image) when the URL resolution fails', async () => {
    mockedPreview.mockRejectedValue(new Error('nope'));
    render(<DriveImageThumbnail attachmentId="a1" alt="photo" />);
    await act(async () => {
      lastCallback?.([{ isIntersecting: true }]);
    });
    await waitFor(() => expect(mockedPreview).toHaveBeenCalled());
    expect(screen.queryByRole('img')).toBeNull();
  });
});
