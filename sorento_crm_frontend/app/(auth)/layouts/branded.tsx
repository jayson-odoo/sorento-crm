'use client';

import { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { AuthBackdrop } from '../components/AuthBackdrop';
import { useSigninBranding } from '../hooks/useSigninBranding';

/** The credential pages: one column of fields, so one column's worth of card. */
const NARROW_ROUTES = [
  '/signin',
  '/signup',
  '/reset-password',
  '/change-password',
  '/verify-email',
];

export function BrandedLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '';
  // Credential pages are one narrow column of fields. The card grew to 1152px at
  // xl anyway, so at 1280 a 320px form sat left-aligned inside a band four times
  // its width and read as a rendering fault. It keeps its own width here; the
  // wide framing stays for the pages that print a table (approval, onboarding,
  // the read-only views).
  //
  // The same set decides who wears the backdrop: only these pages sit centred on
  // an otherwise empty viewport, which is what made the plain background read as
  // unfinished. The portal and the counter-sign page fill their own viewport.
  const narrow = NARROW_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );
  // Fetched only for the pages that render it, and it resolves to "no image" on
  // any failure, so an old or unreachable backend simply leaves the designed
  // default wash on screen.
  const { signinBackgroundUrl } = useSigninBranding(narrow);
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
    <>
      {narrow ? <AuthBackdrop imageUrl={signinBackgroundUrl} /> : null}
      <div
        className={cn(
          'relative flex grow justify-center overflow-y-auto min-h-0 pt-6 pb-6 px-4 sm:px-6 w-full',
          narrow ? 'items-center' : 'items-start',
        )}
      >
        <Card
          className={cn(
            'w-full shrink-0',
            narrow
              ? 'max-w-md auth-card'
              : 'max-w-md sm:max-w-2xl lg:max-w-4xl xl:max-w-6xl',
          )}
        >
          <CardContent className="p-6">{children}</CardContent>
        </Card>
      </div>
    </>
  );
}
