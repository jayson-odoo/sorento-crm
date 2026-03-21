'use client';

import * as React from 'react';
import { useAccountProfileForHeader } from '@/hooks/useAccountProfileForHeader';

/**
 * Topbar / sidebar trigger: shows session user's avatar.
 * Must use forwardRef + spread props so Radix DropdownMenuTrigger asChild can attach ref and handlers.
 */
export const SessionUserAvatar = React.forwardRef<
  HTMLImageElement,
  Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'src'> & { alt?: string }
>(function SessionUserAvatar(
  { className, alt = 'User avatar', ...props },
  ref,
) {
  const { avatarSrc: src } = useAccountProfileForHeader();
  return (
    <img
      ref={ref}
      alt={alt}
      className={className}
      {...props}
      src={src}
    />
  );
});
