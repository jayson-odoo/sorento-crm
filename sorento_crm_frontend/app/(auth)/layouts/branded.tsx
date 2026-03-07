import { ReactNode } from 'react';
import { Card, CardContent } from '@/components/ui/card';

export function BrandedLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex grow justify-center items-start overflow-y-auto min-h-0 pt-6 pb-6 px-6">
      <Card className="w-full max-w-[400px] shrink-0">
        <CardContent className="p-6">{children}</CardContent>
      </Card>
    </div>
  );
}
