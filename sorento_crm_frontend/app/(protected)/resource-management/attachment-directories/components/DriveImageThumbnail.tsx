'use client';

import { useEffect, useRef, useState } from 'react';
import { ImageIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getAttachmentPreviewUrl } from '../../attachments/services/attachmentService';

/**
 * Lazy thumbnail for an `image/*` card in the Drive grid view (UAC G1/G3).
 *
 * The serve/preview URL is only fetched once the card scrolls into view
 * (IntersectionObserver) AND the <img> uses `loading="lazy"`, so off-screen
 * cards never fetch bytes. Non-images render a folder/type icon instead (handled
 * by the caller), so this component is only mounted for images.
 *
 * jsdom has no IntersectionObserver; we guard for it so component tests can
 * assert "no src until in view" by controlling the mock.
 */
export default function DriveImageThumbnail({
  attachmentId,
  alt,
  className,
}: {
  attachmentId: string;
  alt: string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [inView, setInView] = useState(false);
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  // Reveal once the card intersects the viewport.
  useEffect(() => {
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
      { rootMargin: '100px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Resolve the serve URL only after the card is in view.
  useEffect(() => {
    if (!inView || src || failed) return;
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
  }, [inView, src, failed, attachmentId]);

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
          className="h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <ImageIcon className="size-10 text-muted-foreground" />
      )}
    </div>
  );
}
