'use client';

import { useState } from 'react';
import { Loader2, Monitor } from 'lucide-react';

import {
  useSessionsQuery,
  useRevokeSessionMutation,
  useRevokeOtherSessionsMutation,
} from '@/hooks/useSessions';
import type { SessionInfo } from '@/services/sessionService';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardHeading,
  CardToolbar,
} from '@/components/ui/card';

function formatWhen(iso?: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleString();
}

function SessionRow({ session }: { session: SessionInfo }) {
  const revoke = useRevokeSessionMutation();
  return (
    <div className="flex items-center justify-between gap-3 py-3.5">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <Monitor className="size-4" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate font-medium text-mono" title={session.device_label}>
              {session.device_label}
            </span>
            {session.current && (
              <Badge size="sm" variant="success" appearance="light">
                This device
              </Badge>
            )}
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {session.ip_address ? `${session.ip_address} · ` : ''}
            Last active {formatWhen(session.last_seen_at)}
          </div>
        </div>
      </div>

      {session.current ? (
        <span className="shrink-0 text-xs text-muted-foreground">Current session</span>
      ) : (
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="outline" size="sm" disabled={revoke.isPending}>
              {revoke.isPending ? <Loader2 className="size-4 animate-spin" /> : 'Sign out'}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Sign out this device?</AlertDialogTitle>
              <AlertDialogDescription>
                {session.device_label} will be signed out immediately and need to log in again.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => revoke.mutate(session.id)}>
                Sign out
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </div>
  );
}

const CurrentSessions = () => {
  const { data, isLoading, isError, error } = useSessionsQuery();
  const revokeOthers = useRevokeOtherSessionsMutation();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const sessions = data ?? [];
  const hasOthers = sessions.some((s) => !s.current);

  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <div>
            <div className="font-medium text-mono">Active devices</div>
            <div className="text-xs text-muted-foreground">
              Devices currently signed in to your account.
            </div>
          </div>
        </CardHeading>
        <CardToolbar>
          <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
            <AlertDialogTrigger asChild>
              <Button variant="outline" size="sm" disabled={!hasOthers || revokeOthers.isPending}>
                {revokeOthers.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  'Log out all other devices'
                )}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Log out all other devices?</AlertDialogTitle>
                <AlertDialogDescription>
                  Every device except this one will be signed out immediately. This cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => revokeOthers.mutate()}>
                  Log out others
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardToolbar>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading sessions…
          </div>
        ) : isError ? (
          <div className="py-10 text-center text-sm text-destructive">
            {(error as Error)?.message || 'Failed to load sessions.'}
          </div>
        ) : sessions.length === 0 ? (
          <div className="py-10 text-center text-sm text-muted-foreground">
            No active sessions found.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {sessions.map((s) => (
              <SessionRow key={s.id} session={s} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export { CurrentSessions };
