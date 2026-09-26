'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useContact } from '../components/contact-context';
import ContactMediaAccessSection from '../components/ContactMediaAccessSection';
import ContactAccessAgentsTable from '../components/ContactAccessAgentsTable';
import ContactFieldRevealsSection from '../components/ContactFieldRevealsSection';
import ContactChatbotSection from '../components/ContactChatbotSection';

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

      <Card>
        <CardHeader>
          <CardTitle>Field reveals</CardTitle>
        </CardHeader>
        <CardContent>
          <ContactFieldRevealsSection contactId={contactId} />
        </CardContent>
      </Card>

      {/* Chatbot memory lane A (round 3 mockup): ContactChatbotSection now renders its
          OWN cards (Chatbot settings / What the bot knows / Conversations / Open
          orders), matching the mockup's flat card list - no longer nested inside one
          outer "Chatbot" card. */}
      <ContactChatbotSection contactId={contactId} />
    </div>
  );
}
