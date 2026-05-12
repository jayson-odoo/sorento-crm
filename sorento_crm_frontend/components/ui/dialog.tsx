'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { cva, VariantProps } from 'class-variance-authority';
import { X } from 'lucide-react';
import { Dialog as DialogPrimitive } from 'radix-ui';

const dialogContentVariants = cva(
  'flex flex-col fixed outline-0 z-50 border border-border bg-background p-6 shadow-lg shadow-black/5 duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 sm:rounded-lg',
  {
    variants: {
      variant: {
        default: 'left-[50%] top-[50%] max-w-lg translate-x-[-50%] translate-y-[-50%] w-full',
        fullscreen: 'inset-5',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

function Dialog({ modal, ...props }: React.ComponentProps<typeof DialogPrimitive.Root>) {
  // Default to non-modal so the AI assistant bubble (rendered outside the
  // dialog portal) stays scrollable / interactive while a dialog is open.
  // Radix's modal mode wraps the tree in `react-remove-scroll` which blocks
  // wheel/touch events on every element outside the dialog content.
  // Callers can still opt back in by passing `modal={true}` explicitly.
  return <DialogPrimitive.Root data-slot="dialog" modal={modal ?? false} {...props} />;
}

function DialogTrigger({ ...props }: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />;
}

function DialogPortal({ ...props }: React.ComponentProps<typeof DialogPrimitive.Portal>) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />;
}

function DialogClose({ ...props }: React.ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />;
}

function DialogOverlay({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="dialog-overlay"
      className={cn(
        'fixed inset-0 z-50 bg-black/30 [backdrop-filter:blur(4px)] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
        className,
      )}
      {...props}
    />
  );
}

function hasDialogTitleInChildren(children: React.ReactNode): boolean {
  const check = (nodes: React.ReactNode): boolean => {
    return React.Children.toArray(nodes).some((child) => {
      if (!React.isValidElement(child)) return false;
      if (child.type === DialogTitle) return true;
      const grandChildren = (child.props as { children?: React.ReactNode })?.children;
      if (grandChildren !== undefined) return check(grandChildren);
      return false;
    });
  };
  return check(children);
}

function DialogContent({
  className,
  children,
  showCloseButton = true,
  overlay = true,
  variant,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> &
  VariantProps<typeof dialogContentVariants> & {
    showCloseButton?: boolean;
    overlay?: boolean;
  }) {
  const needsFallbackTitle = !hasDialogTitleInChildren(children);
  // Track the moment the actual Content DOM node attaches (i.e. the moment
  // the dialog truly opens). We can't use mount of this React component
  // because Radix evaluates `<DialogContent>` even while the dialog is
  // closed; only the underlying DialogPrimitive.Content DOM node toggles
  // with the open state. The grace window below ignores the trailing
  // pointer/focus event from a DropdownMenu / Popover / Select / ContextMenu
  // item that just opened this dialog — those surfaces unmount during the
  // same click cycle and their last event would otherwise land outside the
  // freshly-opened dialog and instantly close it (`modal={false}` is
  // intentional so the AI assistant bubble outside the portal stays
  // interactive).
  const mountedAtRef = React.useRef<number>(0);
  const contentRefCallback = React.useCallback(
    (node: HTMLDivElement | null) => {
      if (node) {
        mountedAtRef.current = performance.now();
      } else {
        mountedAtRef.current = 0;
      }
    },
    [],
  );
  // Radix wraps these in a CustomEvent whose `target` is the DialogContent itself.
  // The actual click/pointer/focus target is on `event.detail.originalEvent.target`.
  const guardOutsideInteraction = (event: Event) => {
    const detail = (event as CustomEvent<{ originalEvent?: Event }>).detail;
    const original = detail?.originalEvent;
    const target = (original?.target ?? event.target) as Element | null;
    // Keep the AI assistant bubble interactive while a dialog is open.
    if (target && target.closest && target.closest('[data-ai-assistant-root]')) {
      event.preventDefault();
      return;
    }
    // Ignore the trailing pointer/focus event from the Radix surface that
    // *opened* this dialog (dropdown menu / popover / select / context menu).
    // Those surfaces are unmounting during the same tick the dialog mounts;
    // their event would otherwise be misread as an outside click.
    if (
      target &&
      target.closest &&
      target.closest(
        '[data-radix-popper-content-wrapper], [data-radix-menu-content], [data-radix-popover-content], [data-radix-select-content], [data-radix-context-menu-content], [data-slot="dropdown-menu-content"], [data-slot="popover-content"], [data-slot="select-content"], [role="menu"], [role="menuitem"], [role="listbox"], [role="option"]',
      )
    ) {
      event.preventDefault();
      return;
    }
    // Same trailing-event problem when the closing surface was already
    // unmounted by the time the event fires — target lands on body / html.
    // Suppress any outside interaction within a short grace window after
    // mount; this is well under the click-to-real-outside-click latency.
    if (mountedAtRef.current && performance.now() - mountedAtRef.current < 300) {
      event.preventDefault();
      return;
    }
  };
  return (
    <DialogPortal>
      {overlay && <DialogOverlay />}
      <DialogPrimitive.Content
        ref={contentRefCallback}
        data-slot="dialog-content"
        className={cn(dialogContentVariants({ variant }), className)}
        onPointerDownOutside={guardOutsideInteraction}
        onInteractOutside={guardOutsideInteraction}
        onFocusOutside={guardOutsideInteraction}
        {...props}
      >
        {needsFallbackTitle ? (
          <DialogPrimitive.Title className="sr-only">Dialog</DialogPrimitive.Title>
        ) : null}
        {children}
        {showCloseButton && (
          <DialogClose className="cursor-pointer outline-0 absolute end-5 top-5 rounded-sm opacity-60 ring-offset-background transition-opacity hover:opacity-100 focus:outline-hidden disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground">
            <X className="size-4" />
            <span className="sr-only">Close</span>
          </DialogClose>
        )}
      </DialogPrimitive.Content>
    </DialogPortal>
  );
}

export default DialogContent;

const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    data-slot="dialog-header"
    className={cn('flex flex-col space-y-1 text-center sm:text-start mb-5', className)}
    {...props}
  />
);

const DialogFooter = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    data-slot="dialog-footer"
    className={cn('flex flex-col-reverse sm:flex-row sm:justify-end pt-5 sm:space-x-2.5', className)}
    {...props}
  />
);

function DialogTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn('text-lg font-semibold leading-none tracking-tight', className)}
      {...props}
    />
  );
}

const DialogBody = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div data-slot="dialog-body" className={cn('grow', className)} {...props} />
);

function DialogDescription({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn('text-sm text-muted-foreground', className)}
      {...props}
    />
  );
}

export {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
};
