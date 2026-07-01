'use client';

import { useEffect, useRef, useState } from 'react';
import { ImageIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getAttachmentPreviewUrl } from '../../attachments/services/attachmentService';

/**
 * Lazy thumbnail for an `image/*` card in the Drive grid view (UAC G1/G3).
 *
 * Fast path: when the caller supplies `thumbnailUrl` (a freshly-signed ~320px
 * thumbnail from the drive-list response), we render it directly — no extra
 * per-image round-trip and the browser paints a tiny image instead of a full-
 * resolution original (the fix for grid scroll jank; see
 * docs/plans/PLAN-attachment-grid-thumbnails.md).
 *
 * Fallback: with no thumbnail (non-image, or a row uploaded before the backfill)
 * we fetch the original's serve URL once the card scrolls into view
 * (IntersectionObserver) AND the <img> uses `loading="lazy"`, so off-screen
 * cards never fetch bytes.
 *
 * jsdom has no IntersectionObserver; we guard for it so component tests can
 * assert "no src until in view" by controlling the mock.
 */
export default function DriveImageThumbnail({
  attachmentId,
  alt,
  className,
  thumbnailUrl,
}: {
  attachmentId: string;
  alt: string;
  className?: string;
  /** Pre-signed thumbnail URL. When present, used directly (no fetch). */
  thumbnailUrl?: string | null;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [inView, setInView] = useState(false);
  const [src, setSrc] = useState<string | null>(thumbnailUrl ?? null);
  const [failed, setFailed] = useState(false);

  const hasThumb = !!thumbnailUrl;

  // Keep src in sync if the thumbnail URL changes (re-signed / row swapped).
  useEffect(() => {
    if (thumbnailUrl) {
      setSrc(thumbnailUrl);
      setFailed(false);
    }
  }, [thumbnailUrl]);

  // Reveal once the card intersects the viewport. Only needed for the fallback
  // fetch path — with a thumbnail we already have the src.
  useEffect(() => {
    if (hasThumb) return;
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      // Environments without IO (jsdom): don't auto-load; caller-controlled.
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            observer.disconnect();
            break;
          }
        }
      },
      { rootMargin: '600px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasThumb]);

  // Fallback: resolve the original serve URL only after the card is in view.
  useEffect(() => {
    if (hasThumb || !inView || src || failed) return;
    let cancelled = false;
    getAttachmentPreviewUrl(attachmentId)
      .then((url) => {
        if (!cancelled && url) setSrc(url);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [hasThumb, inView, src, failed, attachmentId]);

  return (
    <div
      ref={ref}
      data-testid="drive-image-thumb"
      className={cn(
        'flex items-center justify-center overflow-hidden bg-muted',
        className
      )}
    >
      {src && !failed ? (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          decoding="async"
          className="h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <ImageIcon className="size-10 text-muted-foreground" />
      )}
    </div>
  );
}
