'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  DEFAULT_MESSAGE_PUSH_SCOPE,
  MESSAGE_PUSH_SCOPE_OPTIONS,
  type MessagePushScope,
} from '@/services/messagePushScopeService';
import {
  useMessagePushScopeMutation,
  useMessagePushScopeQuery,
} from '@/hooks/useMessagePushScope';

/**
 * Which contacts' inbound messages buzz my phone (PLAN-message-push).
 *
 * Server-side and device-independent: it governs every device the user has enabled
 * browser notifications on, which is why it sits in its own card rather than inside the
 * per-device opt-in above it, and why it stays settable when this browser cannot push.
 */
export default function MessagePushScopePreference() {
  const { data, isLoading, isError, refetch, isFetching } = useMessagePushScopeQuery();
  const mutation = useMessagePushScopeMutation();

  // While the save is in flight the select shows the chosen value; when it fails
  // react-query drops the variables and the server value is what renders, so the
  // select reverts on its own (AC-M4).
  const value: MessagePushScope =
    (mutation.isPending ? mutation.variables : undefined) ?? data ?? DEFAULT_MESSAGE_PUSH_SCOPE;

  return (
    <Card>
      <CardHeader className="py-4">
        <CardTitle>Message Notifications</CardTitle>
      </CardHeader>
      <CardContent className="py-4 space-y-2">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Label htmlFor="message-push-scope" className="min-w-0">
            Push me about messages from
          </Label>
          <div className="w-full sm:w-[320px]">
            {isLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : (
              <SearchableSelect
                id="message-push-scope"
                value={value}
                onChange={(next) => mutation.mutate(next as MessagePushScope)}
                options={MESSAGE_PUSH_SCOPE_OPTIONS}
                disabled={mutation.isPending || isError}
                wrapOptions
              />
            )}
          </div>
        </div>
        {isError ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-destructive">
              Could not load your saved setting.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void refetch()}
              disabled={isFetching}
            >
              Retry
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Messages only reach devices where you have enabled notifications above.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
