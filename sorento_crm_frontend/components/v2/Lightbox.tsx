'use client';

import type { ReactNode } from 'react';
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Drawer, DrawerBody, DrawerContent, DrawerFooter, DrawerHeader, DrawerTitle } from '@/components/ui/drawer';
import { useIsPhone } from './shell/useViewport';

export interface LightboxProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The accessible name of the surface, always shown. */
  title: string;
  children: ReactNode;
  /** Action buttons, rendered after the body. */
  footer?: ReactNode;
}

/**
 * The v2 lightbox (E-5, decision D7): a centred Dialog above 720 px, a bottom Drawer at 720 px and
 * below, one set of props. It replaces any side Sheet in v2 code. The surfaces bring their own
 * open/close motion.
 */
export function Lightbox({ open, onOpenChange, title, children, footer }: LightboxProps) {
  const isPhone = useIsPhone();

  if (isPhone) {
    return (
      <Drawer open={open} onOpenChange={onOpenChange}>
        <DrawerContent>
          <DrawerHeader>
            <DrawerTitle>{title}</DrawerTitle>
          </DrawerHeader>
          <DrawerBody className="px-4 pb-4">{children}</DrawerBody>
          {footer && <DrawerFooter>{footer}</DrawerFooter>}
        </DrawerContent>
      </Drawer>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogBody>{children}</DialogBody>
        {footer && <DialogFooter>{footer}</DialogFooter>}
      </DialogContent>
    </Dialog>
  );
}
