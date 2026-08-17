'use client';

import * as React from 'react';
import { Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

/**
 * A fact the reader needs once, kept out of the way until they ask for it.
 *
 * The screen was carrying a paragraph under every heading explaining how the feature
 * works. Read once it is a lesson; read every day it is noise, and it pushes the data
 * the person actually came for below the fold. Anything that is genuinely worth saying
 * (why a tab has no Add button, what turning a flag off costs) lives behind this icon.
 *
 * A click rather than a hover: a hover-only hint does not exist on a phone.
 */
export function InfoHint({
  label,
  children,
}: {
  /** What the icon opens, e.g. "About sponsorships". Read out to screen readers. */
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          mode="icon"
          variant="ghost"
          size="sm"
          aria-label={label}
          className="size-6 text-muted-foreground"
        >
          <Info className="size-3.5" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-72 max-w-[calc(100vw-2rem)] text-xs text-muted-foreground"
      >
        {children}
      </PopoverContent>
    </Popover>
  );
}
