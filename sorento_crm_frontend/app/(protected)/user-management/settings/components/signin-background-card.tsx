'use client';

import { LoaderCircleIcon } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { FileDropzone } from '@/components/common/FileDropzone';
import { useSettings } from './settings-context';
import { useSigninBackgroundMutations } from '../hooks/useSigninBackgroundMutations';
import {
  SIGNIN_BACKGROUND_ACCEPT,
  SIGNIN_BACKGROUND_MAX_MB,
} from '../services/signinBackgroundService';

/**
 * The photograph behind the sign-in card.
 *
 * Its own card, and its own save, because it is the one setting on this screen whose value is a
 * file: the General form beside it posts JSON, and threading a file through it would turn every
 * save of a timezone into a multipart request. Picking an image uploads it immediately - the
 * alternative is a second Save the user has to find, for a change they can already see.
 *
 * Removing falls back to the designed default background, which is a finished screen rather than
 * a blank one, so the empty state here is a resting state and not a to-do.
 */
/** One background, one pending action: the id the record actions registry keys it on. */
const SIGNIN_BACKGROUND_ENTITY_ID = 'signin-background';

export function SigninBackgroundCard() {
  const { settings } = useSettings();
  const { upload } = useSigninBackgroundMutations();

  // Remove asks nothing (D7). There is one background, not a row, so the action
  // is parked against the constant below rather than an id the reader never
  // sees; the countdown takes the button's place and Cancel is the way back.
  const removal = useDeferredAction({
    actionKey: 'signin_background.remove',
    entityType: 'signin_background',
    entityId: SIGNIN_BACKGROUND_ENTITY_ID,
    verb: 'Removing',
    subject: 'the sign-in background',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Sign-in background removed',
    invalidateKeys: [['system-settings']],
  });

  const current = settings?.signinBackground ?? null;
  const busy = upload.isPending;

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Sign-in Background</CardTitle>
      </CardHeader>
      <CardContent className="py-8">
        <div className="space-y-4 lg:max-w-[600px] mx-auto">
          <div className="relative aspect-[16/9] w-full overflow-hidden rounded-lg border bg-accent/40">
            {current ? (
              <img
                src={current}
                alt="Current sign-in background"
                className="size-full object-cover"
              />
            ) : (
              <div className="flex size-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
                No image set.
              </div>
            )}
            {busy ? (
              <div className="absolute inset-0 flex items-center justify-center bg-background/60">
                <LoaderCircleIcon className="size-5 animate-spin" />
              </div>
            ) : null}
          </div>

          <FileDropzone
            id="signin-background-file"
            inputTestId="signin-background-file"
            accept={SIGNIN_BACKGROUND_ACCEPT}
            maxSizeMb={SIGNIN_BACKGROUND_MAX_MB}
            disabled={busy}
            files={[]}
            onFilesChange={(files) => {
              const file = files[0];
              if (file) upload.mutate(file);
            }}
            onReject={(file, reason) =>
              toast.error(
                reason === 'size'
                  ? `${file.name} is larger than ${SIGNIN_BACKGROUND_MAX_MB} MB`
                  : `${file.name} is not a JPG, PNG or WebP image`,
              )
            }
            title={
              current ? 'Drop a new image here, or click to browse' : undefined
            }
            aria-label="Sign-in background image"
          />

          {current ? (
            <div className="flex justify-end">
              {removal.countdown ?? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy || removal.isPending}
                  onClick={() => removal.start()}
                >
                  Remove
                </Button>
              )}
            </div>
          ) : null}
        </div>
      </CardContent>

    </Card>
  );
}
