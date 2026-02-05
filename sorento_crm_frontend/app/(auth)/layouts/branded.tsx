import { ReactNode } from 'react';
import { Card, CardContent } from '@/components/ui/card';

export function BrandedLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex grow justify-center items-center p-6 min-h-0">
      <Card className="w-full max-w-[400px]">
        <CardContent className="p-6">{children}</CardContent>
      </Card>
    </div>
  );
}
