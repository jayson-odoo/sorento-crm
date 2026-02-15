import { ReactNode, Suspense } from 'react';
import { Inter } from 'next/font/google';
import { cn } from '@/lib/utils';
import { Metadata } from 'next';
import { DynamicClientProviders } from '@/components/DynamicClientProviders';

const inter = Inter({ subsets: ['latin'] });

import '@/css/styles.css';
import '@/components/keenicons/assets/styles.css';

export const metadata: Metadata = {
  title: {
    template: '%s | Sorento',
    default: 'Sorento', // a default is required when creating a template
  },
};

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html className="h-full" suppressHydrationWarning>
      <body
        className={cn(
          'antialiased flex h-full text-base text-foreground bg-background',
          inter.className,
        )}
      >
        <DynamicClientProviders>
          <Suspense>{children}</Suspense>
        </DynamicClientProviders>
      </body>
    </html>
  );
}
