'use client';

import { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { Card, CardContent } from '@/components/ui/card';

export function BrandedLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '';
  // Portal routes render edge-to-edge on mobile so the contact gets the full
  // viewport width / height. The counter-sign page joins them for the opposite
  // reason: it prints a quotation table wide enough to need every pixel, and
  // the branded card's max-width squeezed it into a narrow column with empty
  // margins either side while the table scrolled inside it. Both own their own
  // width. The branded card framing stays for everything else under the (auth)
  // group.
  if (
    pathname === '/portal' ||
    pathname.startsWith('/portal/') ||
    pathname.startsWith('/quotation-sign/')
  ) {
    return (
      <div className="grow w-full min-h-0 overflow-y-auto bg-background">
        {children}
      </div>
    );
  }
  return (
    <div className="flex grow justify-center items-start overflow-y-auto min-h-0 pt-6 pb-6 px-4 sm:px-6 w-full">
      <Card className="w-full max-w-md sm:max-w-2xl lg:max-w-4xl xl:max-w-6xl shrink-0">
        <CardContent className="p-6">{children}</CardContent>
      </Card>
    </div>
  );
}
