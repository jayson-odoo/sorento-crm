import { ReactNode, Suspense } from 'react';
import { Inter } from 'next/font/google';
import Script from 'next/script';
import { cn } from '@/lib/utils';
import { Metadata } from 'next';
import { DynamicClientProviders } from '@/components/DynamicClientProviders';
import ServiceWorkerRegister from '@/components/pwa/ServiceWorkerRegister';

const inter = Inter({ subsets: ['latin'] });

import '@/css/styles.css';
import '@/components/keenicons/assets/styles.css';

export const metadata: Metadata = {
  title: {
    template: '%s | Sorento',
    default: 'Sorento', // a default is required when creating a template
  },
  manifest: '/manifest.webmanifest',
  appleWebApp: { capable: true, title: 'Sorento', statusBarStyle: 'default' },
  /** Browser tab icon (served from /public). Override by replacing the file or changing this path. */
  icons: {
    icon: [{ url: 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT0W8EVfDgMH4jzzsPWOuT94DxFjJ47M2WkZg&s', type: 'image/svg+xml' }],
    shortcut: 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT0W8EVfDgMH4jzzsPWOuT94DxFjJ47M2WkZg&s',
  },
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  // Auth is resolved entirely client-side (useSession + the /api/auth/token
  // mint, both JWT-only — no DB). We deliberately do NOT call getServerSession
  // here: authOptions uses PrismaAdapter, so seeding the session server-side
  // would hit the DB on every page render — slow/hangs under `next start` +
  // output:standalone, and a null result would flag the user as logged out.
  // The protected layout's debounced redirect tolerates the brief cold-start.
  return (
    <html className="h-full" suppressHydrationWarning>
      <body
        className={cn(
          'antialiased flex h-full text-base text-foreground bg-background',
          inter.className,
        )}
      >
        {/* Snapshot the guide-target hash before Next.js hydration strips it.
            Consumed by GuideTargetSpotlight via sessionStorage. */}
        <script
          id="guide-target-hash-snapshot"
          dangerouslySetInnerHTML={{
            __html:
              "try{if(window.location&&window.location.hash){sessionStorage.setItem('__GUIDE_TARGET_HASH__',window.location.hash);}}catch(e){}",
          }}
        />
        <ServiceWorkerRegister />
        <DynamicClientProviders>
          <Suspense>{children}</Suspense>
        </DynamicClientProviders>
      </body>
    </html>
  );
}
