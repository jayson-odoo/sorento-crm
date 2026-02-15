'use client';

import * as React from 'react';
import * as scrollArea from '@zag-js/scroll-area';
import { useMachine, normalizeProps } from '@zag-js/react';
import { cn } from '@/lib/utils';

interface ScrollAreaZagProps {
  className?: string;
  children: React.ReactNode;
}

/**
 * Bidirectional scroll area (vertical + horizontal) using Zag.js.
 * Use when content can overflow in both axes (e.g. folder list with long names).
 */
export function ScrollAreaZag({ className, children }: ScrollAreaZagProps) {
  const service = useMachine(scrollArea.machine, { id: React.useId() });
  const api = scrollArea.connect(service, normalizeProps);

  return (
    <div
      {...api.getRootProps()}
      className={cn('relative flex flex-1 flex-col min-h-0', className)}
    >
      <div className="flex flex-1 min-h-0 min-w-0">
        <div
          {...api.getViewportProps()}
          className={cn(
            'flex-1 min-w-0 overflow-auto rounded-[inherit]',
            '[scrollbar-width:none] [-ms-overflow-style:none]',
            '[&::-webkit-scrollbar]:hidden'
          )}
        >
          <div {...api.getContentProps()}>{children}</div>
        </div>
        {api.hasOverflowY && (
          <div
            {...api.getScrollbarProps({ orientation: 'vertical' })}
            className="flex touch-none select-none transition-colors h-full w-2 border-l border-l-transparent p-[1px] shrink-0"
          >
            <div
              {...api.getThumbProps({ orientation: 'vertical' })}
              className="relative flex-1 rounded-full bg-border"
            />
          </div>
        )}
      </div>
      {api.hasOverflowX && (
        <div
          {...api.getScrollbarProps({ orientation: 'horizontal' })}
          className="flex touch-none select-none transition-colors h-2 flex-col border-t border-t-transparent p-[1px] shrink-0"
        >
          <div
            {...api.getThumbProps({ orientation: 'horizontal' })}
            className="relative flex-1 rounded-full bg-border"
          />
        </div>
      )}
    </div>
  );
}
