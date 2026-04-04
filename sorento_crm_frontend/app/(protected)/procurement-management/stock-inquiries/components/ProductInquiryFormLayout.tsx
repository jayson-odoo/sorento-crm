'use client';

import { cn } from '@/lib/utils';

export function ProductInquiryFormLayout({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        'rounded-sm border-2 border-foreground/90 bg-background shadow-sm',
        className,
      )}
    >
      <div className="border-b-2 border-foreground/90 px-4 py-3 sm:py-4 text-center bg-muted/30">
        <h2 className="text-sm sm:text-base font-bold uppercase tracking-wide underline underline-offset-[6px] decoration-foreground/90 decoration-2">
          PRODUCT INQUIRY FORM
        </h2>
      </div>
      <div>{children}</div>
    </div>
  );
}

export function InquiryFormTableRow({
  label,
  children,
  className,
  labelClassName,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
  labelClassName?: string;
}) {
  return (
    <div
      className={cn(
        'grid grid-cols-1 sm:grid-cols-[minmax(10rem,12.5rem)_1fr] border-b border-foreground/25 last:border-b-0',
        className,
      )}
    >
      <div
        className={cn(
          'border-b sm:border-b-0 sm:border-r border-foreground/25 bg-muted/50 px-3 py-2 sm:py-2.5 font-bold text-xs sm:text-sm uppercase tracking-wide text-foreground flex items-start sm:items-center',
          labelClassName,
        )}
      >
        {label}
      </div>
      <div className="px-3 py-2 sm:py-2.5 min-h-[2.5rem] text-sm">{children}</div>
    </div>
  );
}

export function InquiryReadValue({
  children,
  empty = '—',
  className,
}: {
  children: React.ReactNode;
  empty?: string;
  className?: string;
}) {
  const isEmpty =
    children == null ||
    (typeof children === 'string' && children.trim() === '');
  return (
    <p
      className={cn(
        'whitespace-pre-wrap break-words font-medium leading-relaxed',
        className,
      )}
    >
      {isEmpty ? <span className="text-muted-foreground font-normal">{empty}</span> : children}
    </p>
  );
}
