import { Suspense } from 'react';
import { ConfigurationHub } from './_components/ConfigurationHub';

export default function ProcessConfigurationIndexPage() {
  return (
    <Suspense fallback={<div className="py-16 text-center text-muted-foreground text-sm">Loading…</div>}>
      <ConfigurationHub />
    </Suspense>
  );
}
