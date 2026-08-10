'use client';

import { ReactNode, useEffect, useState } from 'react';
import { RiErrorWarningFill } from '@remixicon/react';
import {
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { registerRevisionStaleHandler } from '@/lib/revision-fence';

const QueryProvider = ({ children }: { children: ReactNode }) => {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (error) => {
            const message =
              error.message || 'Something went wrong. Please try again.';

            toast.custom(
              () => (
                <Alert variant="mono" icon="destructive" close={false}>
                  <AlertIcon>
                    <RiErrorWarningFill />
                  </AlertIcon>
                  <AlertTitle>{message}</AlertTitle>
                </Alert>
              ),
              {
                position: 'top-center',
              },
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
