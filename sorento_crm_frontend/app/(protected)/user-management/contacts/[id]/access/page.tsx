'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useContact } from '../components/contact-context';
import ContactMediaAccessSection from '../components/ContactMediaAccessSection';
import ContactAccessAgentsTable from '../components/ContactAccessAgentsTable';

export default function ContactAccessPage() {
  const { isLoading, contactId } = useContact();

  if (isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Media Access</CardTitle>
        </CardHeader>
        <CardContent>
          <ContactMediaAccessSection contactId={contactId} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Access Agents</CardTitle>
        </CardHeader>
        <ContactAccessAgentsTable contactId={contactId} />
      </Card>
    </div>
  );
}
