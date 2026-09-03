'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { LoaderCircleIcon, Search, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from '@/lib/toast';
import { createContactAgentAccess } from '../../../access-agents/services/accessAgentService';
import type { ContactAgentAccess } from '../../../access-agents/types/accessAgent.types';

interface ContactOption {
  id: string;
  phone_number: string;
  name?: string | null;
}

interface CopyAccessAgentsFromContactDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentContactId: string;
  currentContactPhone: string;
  currentContactName?: string | null;
  onSuccess?: () => void;
}

export default function CopyAccessAgentsFromContactDialog({
  open,
  onOpenChange,
  currentContactId,
  currentContactPhone,
  currentContactName,
  onSuccess,
}: CopyAccessAgentsFromContactDialogProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [isCopying, setIsCopying] = useState(false);

  const { data: contactsData } = useQuery({
    queryKey: ['contacts-for-copy', searchQuery],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: '1',
        limit: '100',
        sort: 'name',
        dir: 'asc',
        ...(searchQuery.trim() ? { query: searchQuery.trim() } : {}),
      });
      const response = await apiFetch(`/api/user-management/contacts?${params.toString()}`);
      if (!response.ok) throw new Error('Failed to fetch contacts');
      return response.json();
    },
    enabled: open,
  });

  const contacts: ContactOption[] = (contactsData?.data ?? []).filter(
    (c: ContactOption) => c.id !== currentContactId,
  );

  const handleCopy = async () => {
    if (!selectedSourceId) {
      toast.error('Please select an internal user to copy from');
      return;
    }
    setIsCopying(true);
    try {
      const listRes = await apiFetch(
        `/api/user-management/contacts/${selectedSourceId}/access-agents?page=1&limit=1000`,
      );
      if (!listRes.ok) throw new Error('Failed to fetch source access agents');
      const listJson = await listRes.json();
      const sourceAccessAgents: ContactAgentAccess[] = listJson.data ?? [];

      if (sourceAccessAgents.length === 0) {
        toast.info('The selected user has no access agent settings to copy.');
        onOpenChange(false);
        onSuccess?.();
        return;
      }

      let created = 0;
      let skipped = 0;
      for (const acc of sourceAccessAgents) {
        try {
          await createContactAgentAccess(acc.agent_id, {
            respond_contact_phone: currentContactPhone,
            respond_contact_name: currentContactName ?? undefined,
            agent_id: acc.agent_id,
            is_allowed: acc.is_allowed,
            valid_from: acc.valid_from ? new Date(acc.valid_from) : undefined,
            valid_to: acc.valid_to ? new Date(acc.valid_to) : undefined,
          });
          created += 1;
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : String(e);
          if (msg.includes('already exists') || msg.includes('duplicate')) {
            skipped += 1;
          } else {
            throw e;
          }
        }
      }

      toast.success(
        `Copied ${created} access agent setting(s).${skipped > 0 ? ` ${skipped} already existed and were skipped.` : ''}`,
      );
      onOpenChange(false);
      setSelectedSourceId(null);
      setSearchQuery('');
      onSuccess?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to copy access agent settings');
    } finally {
      setIsCopying(false);
    }
  };

  const handleClose = (open: boolean) => {
    if (!open) {
      setSelectedSourceId(null);
      setSearchQuery('');
    }
    onOpenChange(open);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>Copy settings from another user</DialogTitle>
          <DialogDescription>
            Select an internal user to copy all their access agent settings to this user. Existing
            assignments for the same agent will be skipped.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>Search and select internal user</Label>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search by name or phone..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8"
              />
            </div>
          </div>
          <ScrollArea className="h-[240px] rounded-md border">
            <div className="p-2 space-y-0.5">
              {contacts.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  {searchQuery.trim() ? 'No matching contacts.' : 'No other contacts to copy from.'}
                </p>
              ) : (
                contacts.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setSelectedSourceId(selectedSourceId === c.id ? null : c.id)}
                    className={cn(
                      'w-full text-left rounded-md px-3 py-2 text-sm transition-colors',
                      selectedSourceId === c.id
                        ? 'bg-primary/10 text-primary font-medium'
                        : 'hover:bg-accent',
                    )}
                  >
                    <span className="font-medium">{c.name || c.phone_number}</span>
                    {c.name && (
                      <span className="text-muted-foreground ml-1">({c.phone_number})</span>
                    )}
                  </button>
                ))
              )}
            </div>
          </ScrollArea>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)} disabled={isCopying}>
            Cancel
          </Button>
          <Button onClick={handleCopy} disabled={!selectedSourceId || isCopying}>
            {isCopying ? (
              <>
                <LoaderCircleIcon className="mr-2 size-4 animate-spin" />
                Copying...
              </>
            ) : (
              <>
                <Copy className="mr-2 size-4" />
                Copy settings
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
