import { ReactNode, Suspense } from 'react';
import { Inter } from 'next/font/google';
import { cn } from '@/lib/utils';
import { Metadata } from 'next';
import { DynamicClientProviders } from '@/components/DynamicClientProviders';
import ServiceWorkerRegister from '@/components/pwa/ServiceWorkerRegister';

/** Published as a CSS variable so `--font-sans` (css/config.reui.css) can name it and
    every `font-sans` utility resolves to Inter, rather than one generated class doing
    it on <body> alone. The variable has to sit on <html>, which is where Tailwind's
    preflight reads the default font family from. */
const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });

import '@/css/styles.css';
import '@/components/keenicons/assets/styles.css';

export const metadata: Metadata = {
  title: {
    template: '%s | Sorento',
    default: 'Sorento', // a default is required when creating a template
  },
  manifest: '/manifest.webmanifest',
  appleWebApp: { capable: true, title: 'Sorento', statusBarStyle: 'default' },
  /** Served from our own origin (/public), like the manifest's icons - this is
      the icon of an app people are asked to install onto a home screen, so it
      cannot be a hotlink to someone else's CDN (AC-P15). */
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/icon-192.png', type: 'image/png', sizes: '192x192' },
    ],
    shortcut: '/favicon.ico',
    apple: '/icon-192.png',
  },
};

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html className={cn('h-full', inter.variable)} suppressHydrationWarning>
      <body className="antialiased font-sans flex h-full text-base text-foreground bg-background">
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
