'use client';

import { Skeleton } from '@/components/ui/skeleton';
import { useContact } from '../components/contact-context';
import ContactChatbotSection from '../components/ContactChatbotSection';

/**
 * Chatbot memory lane A round 3 (plan 4.5 / mockup): the memory cards (Chatbot
 * settings, What the bot knows, Conversations, Open orders) move off the Access tab
 * onto their own "Chatbot" tab, matching `chatbot-memory-27sep-mockup-contact.html`.
 */
export default function ContactChatbotPage() {
  const { isLoading, contactId } = useContact();

  if (isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }

  return <ContactChatbotSection contactId={contactId} />;
}
