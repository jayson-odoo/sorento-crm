import { ReactNode } from 'react';
import { Card, CardContent } from '@/components/ui/card';

export function BrandedLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex grow justify-center items-start overflow-y-auto min-h-0 pt-6 pb-6 px-4 sm:px-6 w-full">
      <Card className="w-full max-w-md sm:max-w-2xl lg:max-w-4xl xl:max-w-6xl shrink-0">
        <CardContent className="p-6">{children}</CardContent>
      </Card>
    </div>
  );
}
