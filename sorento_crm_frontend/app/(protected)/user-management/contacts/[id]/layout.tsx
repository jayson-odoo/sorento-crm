'use client';

import React, { use, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { KeyRound, MessageSquare, Route, UserPen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import DetailActions from '@/components/common/DetailActions';
import BackToList, { useBackToListHref } from '@/components/common/BackToList';
import { contactsPagerQuery } from '../lib/listQuery';
import PortalLinkButton from '@/components/contacts/PortalLinkButton';
import ContactDeleteDialog from '../components/ContactDeleteDialog';
import { ContactProvider } from './components/contact-context';
import ContactHero from './components/contact-hero';
import { useContactQuery } from './hooks/useContactQuery';
import { contactActions } from '../actions';
import { ContactImpersonateDialog } from '../components/ContactImpersonateDialog';
import type { RespondContact } from '../types/contact.types';

type NavRoutes = Record<
  string,
  {
    title: string;
    icon: React.FC<React.SVGProps<SVGSVGElement>>;
    /** Appended to the record base path; empty for the first tab. */
    segment: string;
    path: string;
  }
>;

export default function ContactLayout({
  params,
  children,
}: {
  params: Promise<{ id: string }>;
  children: React.ReactNode;
}) {
  const { id } = use(params);
  const pathname = usePathname();
  const router = useRouter();
  const backHref = useBackToListHref('/user-management/contacts');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  // Impersonate is on the record now as well as the row (D15), through the one
  // dialog both surfaces share.
  const [impersonateTarget, setImpersonateTarget] = useState<RespondContact | null>(null);
  const [activeTab, setActiveTab] = useState<string>('general');

  const navRoutes = useMemo<NavRoutes>(
    () => ({
      general: {
        title: 'Profile',
        icon: UserPen,
        segment: '',
        path: `/user-management/contacts/${id}`,
      },
      access: {
        title: 'Access',
        icon: KeyRound,
        segment: '/access',
        path: `/user-management/contacts/${id}/access`,
      },
      routing: {
        title: 'Routing',
        icon: Route,
        segment: '/routing',
        path: `/user-management/contacts/${id}/routing`,
      },
      chat: {
        title: 'Chat',
        icon: MessageSquare,
        segment: '/chat',
        path: `/user-management/contacts/${id}/chat`,
      },
    }),
    [id],
  );

  useEffect(() => {
    const found = Object.keys(navRoutes).find((key) => pathname === navRoutes[key].path);
    setActiveTab(found ?? 'general');
  }, [navRoutes, pathname]);

  const { data: contact, isLoading } = useContactQuery(id);


  const handleTabClick = (key: string, path: string) => {
    setActiveTab(key);
    router.push(path);
  };


  const notFound = !isLoading && !contact;

  return (
    <ContactProvider contact={contact} isLoading={isLoading} contactId={id}>
      <Container>
        <PageHeader
          title="Contact Details"
          actions={
            <BackToList listPath="/user-management/contacts" label="Back to contacts" />
          }
        />

        {notFound ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground">Contact not found</p>
            <Button
              variant="outline"
              onClick={() => router.push('/user-management/contacts')}
              className="mt-4"
            >
              Back to Contacts
            </Button>
          </div>
        ) : (
          <>
            <ContactHero
              contact={contact}
              isLoading={isLoading}
              actions={
                <DetailActions
                  pager={{
                    ...contactsPagerQuery,
                    detailPath: '/user-management/contacts',
                    currentId: id,
                    ariaLabel: 'contact',
                    // Stepping keeps the tab being read, so comparing the same
                    // section across contacts does not bounce back to Profile.
                    hrefFor: (nextId, search) =>
                      `/user-management/contacts/${nextId}${
                        navRoutes[activeTab]?.segment ?? ''
                      }${search ? `?${search}` : ''}`,
                  }}
                  actions={
                    contact
                      ? contactActions(contact, {
                          impersonate: () => setImpersonateTarget(contact),
                          remove: () => setDeleteDialogOpen(true),
                        })
                      : []
                  }
                  gearLabel="Contact options"
                  primary={
                    <PortalLinkButton
                      contactId={id}
                      contactLabel={contact?.name ?? contact?.phone_number ?? 'this contact'}
                      canSendViaRespondIo={!!contact?.respond_io_id}
                    />
                  }
                />
              }
            />
            <Tabs defaultValue={activeTab} value={activeTab}>
              <TabsList variant="line" className="mb-5">
                {Object.entries(navRoutes).map(([key, { title, icon: Icon, path }]) => (
                  <TabsTrigger
                    key={key}
                    value={key}
                    disabled={isLoading}
                    onClick={() => handleTabClick(key, path)}
                  >
                    <Icon />
                    <span>{title}</span>
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            {children}
          </>
        )}
        <ContactImpersonateDialog
          contact={impersonateTarget}
          onClose={() => setImpersonateTarget(null)}
        />
      </Container>

      <ContactDeleteDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        contact={contact ?? null}
        onSuccess={() => router.push(backHref)}
      />
    </ContactProvider>
  );
}
