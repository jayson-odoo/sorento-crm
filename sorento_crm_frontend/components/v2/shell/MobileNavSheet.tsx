'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { MENU_SIDEBAR } from '@/config/menu.config';
import { SidebarMenu } from '@/app/components/layouts/demo1/components/sidebar-menu';
import { Drawer, DrawerBody, DrawerContent, DrawerTitle } from '@/components/ui/drawer';

/** The phone navigation drawer (E-1): a vaul drawer from the start edge, closed on every route change. */
export function MobileNavSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const pathname = usePathname();
  useEffect(() => {
    onOpenChange(false);
    // Only a route change closes it; onOpenChange identity is not a reason to.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  return (
    <Drawer open={open} onOpenChange={onOpenChange} direction="left" shouldScaleBackground={false}>
      <DrawerContent className="w-[280px] gap-0 p-0">
        <DrawerTitle className="sr-only">Navigation menu</DrawerTitle>
        <DrawerBody className="overflow-y-auto p-0">
          <SidebarMenu menu={MENU_SIDEBAR} />
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}
