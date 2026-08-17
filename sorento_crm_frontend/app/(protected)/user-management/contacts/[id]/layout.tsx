'use client';

import React, { use, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { KeyRound, MessageSquare, MoveLeft, Route, Trash2, UserPen } from 'lucide-react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import RecordNavigation from '@/components/common/RecordNavigation';
import PortalLinkButton from '@/components/contacts/PortalLinkButton';
import ContactDeleteDialog from '../components/ContactDeleteDialog';
import { ContactProvider } from './components/contact-context';
import ContactHero from './components/contact-hero';
import { useContactQuery } from './hooks/useContactQuery';
import { useContactNavigationQuery } from './hooks/useContactNavigationQuery';

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
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
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

  const { data: navigationData } = useContactNavigationQuery();
  const navigationItems = navigationData?.data ?? [];

  const handleTabClick = (key: string, path: string) => {
    setActiveTab(key);
    router.push(path);
  };

  // Prev/next keeps the tab the user is reading, so stepping through contacts to
  // compare the same section does not bounce back to Profile on every record.
  const handleRecordSelect = (nextId: string) => {
    const segment = navRoutes[activeTab]?.segment ?? '';
    router.push(`/user-management/contacts/${nextId}${segment}`);
  };

  const notFound = !isLoading && !contact;

  return (
    <ContactProvider contact={contact} isLoading={isLoading} contactId={id}>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Contact Details</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/user-management/contacts">
                    User Management
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Contacts</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <RecordNavigation
              currentId={id}
              items={navigationItems}
              basePath="/user-management/contacts"
              onSelect={handleRecordSelect}
            />
            <PortalLinkButton
              contactId={id}
              contactLabel={contact?.name ?? contact?.phone_number ?? 'this contact'}
              canSendViaRespondIo={!!contact?.respond_io_id}
            />
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(true)}
              disabled={!contact}
              className="text-destructive border-destructive/50 hover:bg-destructive/10"
            >
              <Trash2 className="size-4 mr-2" />
              Delete contact
            </Button>
            <Button asChild variant="outline">
              <button onClick={() => router.push('/user-management/contacts')}>
                <MoveLeft /> Back to contacts
              </button>
            </Button>
          </ToolbarActions>
        </Toolbar>

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
            <ContactHero contact={contact} isLoading={isLoading} />
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
      </Container>

      <ContactDeleteDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        contact={contact ?? null}
        onSuccess={() => router.push('/user-management/contacts')}
      />
    </ContactProvider>
  );
}
