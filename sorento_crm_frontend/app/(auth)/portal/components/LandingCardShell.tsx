'use client';

import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * The landing card's frame, shared by the submission cards (`SubmissionCard`) and the asks to-do
 * card (`AskCard`): the rounded, tinted, pressable box. The caller supplies the tint, the press
 * wiring (`tabIndex`, `onClick`, `onKeyDown`, and a `role` where it opens a link) and the children,
 * which include the top-right slot (the caller positions it `absolute top-2 right-2`, the shell
 * is `relative`).
 */
export function LandingCardShell({
  tintClass,
  className,
  children,
  ...press
}: { tintClass: string; children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...press}
      className={cn(
        `relative block rounded-lg border ${tintClass} px-3.5 py-3 pr-3 hover:brightness-95 active:brightness-90 transition-[filter] select-none cursor-pointer`,
        className,
      )}
    >
      {children}
    </div>
  );
}
