'use client';

import { use, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { MoveLeft } from 'lucide-react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Pencil, RefreshCw, Trash2 } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { formatDate } from '@/lib/helpers';
import { useState } from 'react';
import { toast } from 'sonner';
import ContactAccessAgentsTable from './components/ContactAccessAgentsTable';
import ContactEditDialog from './components/ContactEditDialog';
import ContactDeleteDialog from '../components/ContactDeleteDialog';
import PortalLinkButton from '@/components/contacts/PortalLinkButton';
import type { RespondContact } from '../types/contact.types';
import RecordNavigation from '@/components/common/RecordNavigation';

export default function ContactDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
    }),
    [],
  );

  const { data: contact, isLoading } = useQuery({
    queryKey: ['respond-contact', id],
    queryFn: async () => {
      const response = await apiFetch(`/api/user-management/contacts/${id}`);
      if (!response.ok) throw new Error('Failed to fetch contact');
      const data = await response.json();
      return data as RespondContact;
    },
    enabled: !!id,
  });

  const { data: navigationData } = useQuery({
    queryKey: ['respond-contacts-nav', navigationParams],
    queryFn: async () => {
      const sortField = navigationParams.sorting?.[0]?.id || 'created_at';
      const sortDirection = navigationParams.sorting?.[0]?.desc ? 'desc' : 'asc';
      const params = new URLSearchParams({
        page: String(navigationParams.pageIndex + 1),
        limit: String(navigationParams.pageSize),
        sort: sortField,
        dir: sortDirection,
        ...(navigationParams.searchQuery ? { query: navigationParams.searchQuery } : {}),
      });
      const response = await apiFetch(`/api/user-management/contacts?${params.toString()}`);
      if (!response.ok) throw new Error('Failed to fetch contacts');
      return response.json();
    },
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });
  const navigationItems = navigationData?.data ?? [];

  const syncContactMutation = useMutation({
    mutationFn: async (contactId: string) => {
      const response = await apiFetch(`/api/user-management/contacts/${contactId}/sync`, {
        method: 'POST',
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.message || error.message || 'Failed to sync contact');
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['respond-contact', id] });
      queryClient.invalidateQueries({ queryKey: ['respond-contacts'] });
      toast.success('Contact synced successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to sync contact');
    },
  });

  const handleSync = () => {
    if (contact) {
      syncContactMutation.mutate(contact.id);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!contact) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Contact not found</p>
        <Button variant="outline" onClick={() => router.push('/user-management/contacts')} className="mt-4">
          Back to Contacts
        </Button>
      </div>
    );
  }

  return (
    <>
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
                  <BreadcrumbLink href="/user-management/contacts">User Management</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Internal Users</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <RecordNavigation
              currentId={id}
              items={navigationItems}
              basePath="/user-management/contacts"
            />
            <PortalLinkButton
              contactId={id}
              contactLabel={contact?.name ?? contact?.phone_number ?? id}
              canSendViaRespondIo={!!contact?.respond_io_id}
            />
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(true)}
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
      </Container>

      <Container>
        <Card>
          <CardHeader>
            <CardTitle>Contact Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm text-muted-foreground">Phone Number</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditDialogOpen(true)}
                    className="h-6 w-6 p-0"
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                </div>
                <p className="font-medium font-mono">{contact.phone_number}</p>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm text-muted-foreground">Name</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleSync}
                    disabled={syncContactMutation.isPending}
                    className="h-6 w-6 p-0"
                    title="Sync from Respond.io"
                  >
                    <RefreshCw className={`h-3 w-3 ${syncContactMutation.isPending ? 'animate-spin' : ''}`} />
                  </Button>
                </div>
                <p className="font-medium">{contact.name || <span className="text-muted-foreground">Not set</span>}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">First name</p>
                <p className="font-medium">
                  {contact.first_name || <span className="text-muted-foreground">—</span>}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Last name</p>
                <p className="font-medium">
                  {contact.last_name || <span className="text-muted-foreground">—</span>}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">User Type</p>
                <p className="font-medium">{contact.user_type || <span className="text-muted-foreground">—</span>}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Respond.io ID</p>
                <p className="font-medium font-mono text-sm">{contact.respond_io_id ?? <span className="text-muted-foreground">—</span>}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Created At</p>
                <p className="font-medium">{formatDate(new Date(contact.created_at))}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Updated At</p>
                <p className="font-medium">{formatDate(new Date(contact.updated_at))}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </Container>

      <Container>
        <Card>
          <CardHeader>
            <CardTitle>Access Agents</CardTitle>
          </CardHeader>
          <ContactAccessAgentsTable contactId={id} />
        </Card>
      </Container>

      <ContactEditDialog
        open={editDialogOpen}
        closeDialog={() => setEditDialogOpen(false)}
        contact={contact}
      />

      <ContactDeleteDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        contact={contact}
        onSuccess={() => router.push('/user-management/contacts')}
      />
    </>
  );
}
