'use client';

import { Card, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useContact } from '../components/contact-context';
import ContactCsRoutingRules from '../components/routing/ContactCsRoutingRules';

export default function ContactRoutingPage() {
  const { isLoading, contactId } = useContact();

  if (isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Customer Service Assignment</CardTitle>
      </CardHeader>
      <ContactCsRoutingRules contactId={contactId} />
    </Card>
  );
}
