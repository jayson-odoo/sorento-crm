/**
 * The shared stored-image component (IMAGE-UNIFY "Frontend"): it draws the size asked for, steps
 * DOWN a size when one is missing or fails, never up to the original, then shows the placeholder.
 */
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { AttachmentImage } from './AttachmentImage';

const urls = { thumbUrl: 'https://cdn.test/a.thumb.jpg', mediumUrl: 'https://cdn.test/a.medium.jpg', url: 'https://cdn.test/a.png' };

describe('AttachmentImage', () => {
  it('a thumb is the thumb rendition, never the original', () => {
    const { container } = render(<AttachmentImage {...urls} />);
    const img = container.querySelector('img')!;
    expect(img).toHaveAttribute('src', urls.thumbUrl);
    expect(img).toHaveAttribute('loading', 'lazy');
  });

  it('a thumb that is not ready shows the placeholder, not the original', () => {
    const { container } = render(
      <AttachmentImage thumbUrl={null} url={urls.url} fallback={<span>No picture</span>} />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('No picture')).toBeInTheDocument();
  });

  it('a thumb that fails to load shows the placeholder', () => {
    const { container } = render(<AttachmentImage {...urls} fallback={<span>No picture</span>} />);
    fireEvent.error(container.querySelector('img')!);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('No picture')).toBeInTheDocument();
  });

  it('a medium that fails steps down to the thumb', () => {
    const { container } = render(<AttachmentImage {...urls} size="medium" />);
    expect(container.querySelector('img')).toHaveAttribute('src', urls.mediumUrl);
    fireEvent.error(container.querySelector('img')!);
    expect(container.querySelector('img')).toHaveAttribute('src', urls.thumbUrl);
  });
});
