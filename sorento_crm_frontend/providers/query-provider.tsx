'use client';

import { ReactNode, useEffect, useState } from 'react';
import { RiErrorWarningFill } from '@remixicon/react';
import {
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { registerRevisionStaleHandler } from '@/lib/revision-fence';
import { pendingEntityStore } from '@/lib/pending-entity-store';

const QueryProvider = ({ children }: { children: ReactNode }) => {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        // The shared default every query gets unless a hook names a reason
        // not to (M4 list latency): retry once, treat data as fresh for 30s,
        // and do not refetch merely because the tab regained focus - on
        // origin/main, 173 hooks set it to false themselves and roughly 410
        // did not (so they refetched on focus); this default replaces both.
        // A hook with a genuinely different staleTime or refetchInterval
        // (the conversation surfaces' polling, a pager's Infinity) still
        // sets its own - this is only the floor every OTHER hook inherits.
        defaultOptions: {
          queries: {
            retry: 1,
            staleTime: 30_000,
            refetchOnWindowFocus: false,
          },
        },
        queryCache: new QueryCache({
          onError: (error, query) => {
            // A query may opt out of the shared toast with `meta: { silent: true }`.
            // Some reads are context beside the thing the user came for (a product
            // photo, say) and their failure is reported in place, on the panel that
            // asked; a page-level destructive toast for one of those tells the user
            // their work is in trouble when nothing about it is.
            if (query.meta?.silent) return;

            // A record the user has just watched a delete commit on is GONE, and
            // every query still keyed on it now 404s: the detail read, its tabs,
            // its counts. That is the answer we asked for, not a stack of red
            // toasts (S6 feedback C). The guard on the page says "Already
            // deleted" once and returns the reader to the list.
            if (
              query.queryKey.some(
                (part) =>
                  typeof part === 'string' && pendingEntityStore.wasDeletedId(part),
              )
            ) {
              return;
            }

            const message =
              error.message || 'Something went wrong. Please try again.';

            // When a user hits a page without permission, every query 403s
            // independently. Without deduplication that produces a stack of red
            // toasts. Sonner dedupes by `id`, so a single fixed id collapses
            // them into one.
            const isPermissionError =
              message.startsWith('Permission required:') ||
              message.startsWith('One of these permissions required:');

            if (isPermissionError) {
              toast.custom(
                (id) => (
                  <Alert variant="mono" icon="destructive" close onClose={() => toast.dismiss(id)}>
                    <AlertIcon>
                      <RiErrorWarningFill />
                    </AlertIcon>
                    <AlertTitle>
                      {"You don't have permission to view this. Ask an administrator."}
                    </AlertTitle>
                  </Alert>
                ),
                { id: 'permission-denied', duration: Infinity },
              );
              return;
            }

            toast.custom(
              (id) => (
                <Alert variant="mono" icon="destructive" close onClose={() => toast.dismiss(id)}>
                  <AlertIcon>
                    <RiErrorWarningFill />
                  </AlertIcon>
                  <AlertTitle>{message}</AlertTitle>
                </Alert>
              ),
              { duration: Infinity },
            );
          },
        }),
      }),
  );

  // The revision fence refuses an office write aimed at a superseded version
  // (UAC C-bis). The refusal is only half an answer: the user is still looking
  // at the version that no longer exists, so refetch and put the new revision on
  // screen. A blanket invalidation is deliberate - a conflict is rare, and the
  // banner, the timeline, the list badge and the record itself all have to move
  // together, so pinning a key list here would only rot.
  // The deferred-action follow-through invalidates lists after a window lapses
  // with nothing mounted, so it needs the app's ONE client rather than a second
  // one of its own (S6 feedback A).
  useEffect(() => {
    pendingEntityStore.registerQueryClient(queryClient);
    return () => pendingEntityStore.registerQueryClient(null);
  }, [queryClient]);

  useEffect(() => {
    registerRevisionStaleHandler(() => {
      void queryClient.invalidateQueries();
    });
    return () => registerRevisionStaleHandler(null);
  }, [queryClient]);

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

export { QueryProvider };
