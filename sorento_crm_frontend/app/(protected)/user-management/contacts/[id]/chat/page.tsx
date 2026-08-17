'use client';

import { Skeleton } from '@/components/ui/skeleton';
import { useContact } from '../components/contact-context';
import ContactChatHistorySection from '../components/ContactChatHistorySection';

export default function ContactChatPage() {
  const { contact, isLoading } = useContact();

  if (isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }

  return <ContactChatHistorySection respondIoId={contact?.respond_io_id ?? null} />;
}
