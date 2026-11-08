'use client';

/**
 * The secondary red-outline Reject of a form's header: the stock inquiry's purchasing Reject, also
 * used by the new product application (owner 8 Nov: "like stock inquiry has a reject button as a
 * secondary button"). One component so the two cannot drift.
 */

import type { ComponentProps } from 'react';
import { XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Props = Omit<ComponentProps<typeof Button>, 'variant' | 'size' | 'children'>;

export function RejectOutlineButton({ className, ...rest }: Props) {
  return (
    <Button
      variant="outline"
      size="sm"
      className={`text-destructive border-destructive/40 hover:bg-destructive/10${className ? ` ${className}` : ''}`}
      {...rest}
    >
      <XCircle className="size-4 mr-1" />
      Reject
    </Button>
  );
}
