import * as React from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { ChevronRight, MoreHorizontal } from 'lucide-react';
import { Slot as SlotPrimitive } from 'radix-ui';

function Breadcrumb({
  ...props
}: React.ComponentProps<'nav'> & {
  separator?: React.ReactNode;
}) {
  return <nav data-slot="breadcrumb" aria-label="breadcrumb" {...props} />;
}

function BreadcrumbList({ className, ...props }: React.ComponentProps<'ol'>) {
  return (
    <ol
      data-slot="breadcrumb-list"
      className={cn('flex flex-wrap items-center gap-1.5 break-words text-sm text-muted-foreground', className)}
      {...props}
    />
  );
}

function BreadcrumbItem({ className, ...props }: React.ComponentProps<'li'>) {
  return <li data-slot="breadcrumb-item" className={cn('inline-flex items-center gap-1.5', className)} {...props} />;
}

function BreadcrumbLink({
  asChild,
  className,
  href,
  ...props
}: React.ComponentProps<'a'> & {
  asChild?: boolean;
}) {
  const classes = cn('transition-colors hover:text-foreground', className);

  // Caller controls the element (e.g. wraps a next/link itself).
  if (asChild) {
    return <SlotPrimitive.Slot data-slot="breadcrumb-link" className={classes} {...props} />;
  }

  // Internal links MUST navigate client-side. A plain <a> triggers a full page
  // reload, which cold-starts the client-side session + token cache — the window
  // where useSession momentarily reads `unauthenticated` (random logout) or the
  // token mint blips (`Authentication required`). next/link keeps the SPA context
  // alive so neither happens. Fixing it here fixes every breadcrumb app-wide.
  if (typeof href === 'string' && href.startsWith('/')) {
    return <Link data-slot="breadcrumb-link" href={href} className={classes} {...props} />;
  }

  return <a data-slot="breadcrumb-link" href={href} className={classes} {...props} />;
}

function BreadcrumbPage({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      data-slot="breadcrumb-page"
      role="link"
      aria-disabled="true"
      aria-current="page"
      className={cn('font-normal text-foreground', className)}
      {...props}
    />
  );
}

const BreadcrumbSeparator = ({ children, className, ...props }: React.ComponentProps<'li'>) => (
  <li
    data-slot="breadcrumb-separator"
    role="presentation"
    aria-hidden="true"
    className={cn('[&>svg]:w-3.5 [&>svg]:h-3.5', className)}
    {...props}
  >
    {children ?? <ChevronRight className="rtl:rotate-180" />}
  </li>
);

const BreadcrumbEllipsis = ({ className, ...props }: React.ComponentProps<'span'>) => (
  <span
    data-slot="breadcrumb-ellipsis"
    role="presentation"
    aria-hidden="true"
    className={cn('flex h-9 w-9 items-center justify-center', className)}
    {...props}
  >
    <MoreHorizontal className="h-4 w-4" />
    <span className="sr-only">More</span>
  </span>
);

export {
  Breadcrumb,
  BreadcrumbEllipsis,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
};
