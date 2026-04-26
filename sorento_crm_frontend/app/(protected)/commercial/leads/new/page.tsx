import { Metadata } from 'next';
import { Suspense } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import CreateLeadWizard from '../components/CreateLeadWizard';

export const metadata: Metadata = {
  title: 'Create lead',
};

export default function NewCommercialLeadPage() {
  return (
    <Suspense
      fallback={
        <div className="bg-[#f9fafb] py-16">
          <Skeleton className="mx-auto h-96 w-full max-w-[960px]" />
        </div>
      }
    >
      <CreateLeadWizard />
    </Suspense>
  );
}
