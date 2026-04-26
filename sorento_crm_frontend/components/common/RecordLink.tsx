'use client';

import * as React from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';

export type RecordLinkProps = {
  href: string;
  children: React.ReactNode;
  className?: string;
  external?: boolean;
};

/**
 * Hyperlink for important record references inside listings (project, customer, order, etc.).
 * Always rendered in the brand "record red" so it's clear it navigates to the record's view page.
 * Stops row-click propagation so the row's edit-navigation doesn't fire.
 */
export function RecordLink({ href, children, className, external = false }: RecordLinkProps) {
  const stop = (e: React.MouseEvent) => e.stopPropagation();
  const cls = cn('text-red-600 hover:text-red-700 hover:underline truncate', className);
  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer noopener" onClick={stop} className={cls}>
        {children}
      </a>
    );
  }
  return (
    <Link href={href} onClick={stop} className={cls}>
      {children}
    </Link>
  );
}
