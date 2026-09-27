'use client';

import type React from 'react';
import { ChevronDown, Copy, CornerUpLeft } from 'lucide-react';

import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useReducedMotion } from '@/lib/motion';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import { useSwipeToReply } from './useSwipeToReply';

interface MessageBubbleActionsProps {
  /** Off = the plain bubble every other thread surface renders (AC-RT-6). */
  enabled: boolean;
  /** Absent = the menu offers Copy only and there is no swipe (AC-RT-5). */
  onReply?: () => void;
  /** What Copy writes: the text the bubble shows. Empty = no Copy item. */
  copyText: string;
  className: string;
  /** The in-thread search's current match (read by the scroll-back tests). */
  activeMatch?: boolean;
  children: React.ReactNode;
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success('Copied');
  } catch {
    toast.error('Could not copy this message');
  }
}

/**
 * One message bubble with WhatsApp's message actions (#1317): a chevron at the
 * corner on hover and a right-click menu on desktop, swipe right and long press
 * on a phone. Reply and Copy only. Long press is Radix ContextMenu's own touch
 * behaviour, so the two menus are the same component family.
 */
export default function MessageBubbleActions({
  enabled,
  onReply,
  copyText,
  className,
  activeMatch = false,
  children,
}: MessageBubbleActionsProps) {
  const prefersReducedMotion = useReducedMotion();
  const swipe = useSwipeToReply({ enabled: enabled && !!onReply, onReply: () => onReply?.() });

  if (!enabled) {
    return (
      <div
        data-testid="message-bubble"
        data-active-match={activeMatch ? 'true' : undefined}
        className={className}
      >
        {children}
      </div>
    );
  }

  const hasCopy = !!copyText.trim();
  const items = (Item: typeof ContextMenuItem | typeof DropdownMenuItem) => (
    <>
      {onReply && (
        <Item onSelect={() => onReply()}>
          <CornerUpLeft />
          Reply
        </Item>
      )}
      {hasCopy && (
        <Item onSelect={() => void copyToClipboard(copyText)}>
          <Copy />
          Copy
        </Item>
      )}
    </>
  );

  return (
    <>
      <ContextMenu>
        <ContextMenuTrigger asChild>
          <div
            data-testid="message-bubble"
            data-active-match={activeMatch ? 'true' : undefined}
            // pan-y: vertical scrolling stays the browser's, horizontal travel
            // comes to the swipe handlers. Coarse pointers lose text selection
            // (a long press is the menu there); desktop keeps it.
            className={cn(
              'group/bubble relative touch-pan-y [@media(pointer:coarse)]:select-none',
              className,
            )}
            style={
              onReply
                ? {
                    transform: `translateX(${swipe.offset}px)`,
                    transition:
                      swipe.dragging || prefersReducedMotion
                        ? 'none'
                        : 'transform var(--duration-fast) var(--ease-standard)',
                  }
                : undefined
            }
            {...swipe.handlers}
          >
            {onReply && (
              // Rides just outside the bubble's leading edge, so it shows in
              // the gap the swipe opens, for incoming and outgoing alike.
              <span
                aria-hidden
                data-testid="swipe-reply-icon"
                className="pointer-events-none absolute end-full top-1/2 me-2 flex size-7 -translate-y-1/2 items-center justify-center rounded-full bg-black/10 text-zinc-700 dark:bg-white/15 dark:text-zinc-200"
                style={{ opacity: swipe.progress }}
              >
                <CornerUpLeft className="size-4" />
              </span>
            )}
            {(onReply || hasCopy) && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    aria-label="Message actions"
                    className="absolute end-1 top-1 z-10 hidden size-5 items-center justify-center rounded-full bg-inherit text-zinc-500 opacity-0 shadow-sm group-hover/bubble:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100 [@media(hover:hover)]:flex dark:text-zinc-300"
                  >
                    <ChevronDown className="size-4" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">{items(DropdownMenuItem)}</DropdownMenuContent>
              </DropdownMenu>
            )}
            {children}
          </div>
        </ContextMenuTrigger>
        {(onReply || hasCopy) && <ContextMenuContent>{items(ContextMenuItem)}</ContextMenuContent>}
      </ContextMenu>
    </>
  );
}
