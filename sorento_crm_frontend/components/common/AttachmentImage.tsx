'use client';

import { useState, type ReactNode } from 'react';
import { ImageIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * The ONE way a stored image is drawn on a screen (IMAGE-UNIFY P3 shape,
 * `documentation/plans/resources/PLAN-image-unify-03nov.md` "Frontend").
 *
 * It takes the URLs the backend sends (the rendition service's `thumb_url` / `medium_url` and the
 * original `url`) and never builds one. `size` picks the first choice; a URL that is missing or
 * fails to load steps DOWN a size (original, medium, thumb), never up to a bigger file, and when
 * none is left the `fallback` (a muted picture icon by default) is shown. So a small picture is
 * never the original. Lazy and async-decoded, from `DriveImageThumbnail`.
 */
export function AttachmentImage({
  thumbUrl,
  mediumUrl,
  url,
  size = 'thumb',
  alt = '',
  className,
  fallback,
}: {
  thumbUrl?: string | null;
  mediumUrl?: string | null;
  url?: string | null;
  size?: 'thumb' | 'medium' | 'original';
  alt?: string;
  className?: string;
  fallback?: ReactNode;
}) {
  const order =
    size === 'thumb'
      ? [thumbUrl]
      : size === 'medium'
        ? [mediumUrl, thumbUrl]
        : [url, mediumUrl, thumbUrl];
  const candidates = order.filter((value): value is string => Boolean(value));
  // Links that failed to load; a new picture (another pick, a re-signed link) is a new URL.
  const [failed, setFailed] = useState<string[]>([]);
  const src = candidates.find((candidate) => !failed.includes(candidate));
  if (!src) {
    return (
      <>
        {fallback ?? (
          <span className={cn('flex items-center justify-center bg-muted', className)}>
            <ImageIcon className="size-4 text-muted-foreground" />
          </span>
        )}
      </>
    );
  }
  return (
    <img
      key={src}
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      className={className}
      onError={() => setFailed((dead) => [...dead, src])}
    />
  );
}

export default AttachmentImage;
