'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  CardHeader,
  CardHeading,
  CardTitle,
} from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { LoaderCircleIcon } from 'lucide-react';
import {
  getAccountPasswordSchema,
  AccountPasswordSchemaType,
} from '../../forms/account-password-schema';
import { useSetPasswordMutation } from '../hooks/useSetPasswordMutation';

interface Props {
  open: boolean;
  closeDialog: () => void;
  /** false = "Set a password" (a phone-only user has none yet); true = "Change password". */
  hasPassword: boolean;
}

const ChangePasswordDialog = ({ open, closeDialog, hasPassword }: Props) => {
  const title = hasPassword ? 'Change password' : 'Set a password';

  const form = useForm<AccountPasswordSchemaType>({
    resolver: zodResolver(getAccountPasswordSchema(hasPassword)),
    defaultValues: {
      currentPassword: '',
      newPassword: '',
      confirmNewPassword: '',
    },
    mode: 'onTouched',
  });

  useEffect(() => {
    if (open) {
      form.reset();
    }
  }, [open, form]);

  const mutation = useSetPasswordMutation({ onSuccess: closeDialog });
  const isProcessing = mutation.status === 'pending';

  const handleSubmit = (values: AccountPasswordSchemaType) => {
    mutation.mutate({
      current_password: hasPassword ? values.currentPassword : undefined,
      new_password: values.newPassword,
    });
  };

  return (
    <Dialog open={open} onOpenChange={closeDialog}>
      <DialogContent>
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <CardHeader className="py-5">
          <CardHeading>
            <CardTitle>{title}</CardTitle>
          </CardHeading>
        </CardHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="space-y-6"
          >
            {mutation.status === 'error' && (
              <Alert variant="destructive">
                <AlertDescription>{mutation.error.message}</AlertDescription>
              </Alert>
            )}

            {hasPassword && (
              <FormField
                control={form.control}
                name="currentPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Current password</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder="Enter current password"
                        autoComplete="current-password"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            <FormField
              control={form.control}
              name="newPassword"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>New password</FormLabel>
                  <FormControl>
                    <Input
                      type="password"
                      placeholder="Enter new password"
                      autoComplete="new-password"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="confirmNewPassword"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Confirm new password</FormLabel>
                  <FormControl>
                    <Input
                      type="password"
                      placeholder="Re-enter new password"
                      autoComplete="new-password"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!form.formState.isDirty || isProcessing}
              >
                {isProcessing && <LoaderCircleIcon className="animate-spin" />}
                Save
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default ChangePasswordDialog;
