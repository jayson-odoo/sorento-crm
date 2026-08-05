'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  AppWindowMac,
  Bell,
  LoaderCircleIcon,
  MailWarning,
  UserPlus,
  Users,
} from 'lucide-react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import DiscontinuedNotifyCompaniesCard from './DiscontinuedNotifyCompaniesCard';
import { apiFetch } from '@/lib/api';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Form, FormControl, FormField, FormItem } from '@/components/ui/form';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useSettings } from '../components/settings-context';
import {
  NotificationSettingsSchema,
  NotificationSettingsSchemaType,
} from '../forms/notification-settings-schema';

const notificationSettings = [
  {
    label: 'Stock Alerts',
    description: 'Notify when stock reaches the threshold.',
    emailField: 'notifyStockEmail',
    webField: 'notifyStockWeb',
    roleIdsField: 'notifyStockRoleIds',
  },
  {
    label: 'New Delivery Orders',
    description: 'Notify when new delivery orders are received.',
    emailField: 'notifyNewOrderEmail',
    webField: 'notifyNewOrderWeb',
    roleIdsField: 'notifyNewOrderRoleIds',
  },
  {
    label: 'Delivery Order Status Updates',
    description: 'Notify when a delivery order status is updated.',
    emailField: 'notifyOrderStatusUpdateEmail',
    webField: 'notifyOrderStatusUpdateWeb',
    roleIdsField: 'notifyOrderStatusUpdateRoleIds',
  },
  {
    label: 'Payment Failures',
    description: 'Notify when a payment failure occurs.',
    emailField: 'notifyPaymentFailureEmail',
    webField: 'notifyPaymentFailureWeb',
    roleIdsField: 'notifyPaymentFailureRoleIds',
  },
  {
    label: 'System Errors',
    description: 'Notify when system errors occur.',
    emailField: 'notifySystemErrorFailureEmail',
    webField: 'notifySystemErrorWeb',
    roleIdsField: 'notifySystemErrorRoleIds',
  },
];

const NotificationSettingsPage = () => {
  const queryClient = useQueryClient();
  const { settings, roles } = useSettings();

  const form = useForm<NotificationSettingsSchemaType>({
    resolver: zodResolver(NotificationSettingsSchema),
    defaultValues: notificationSettings.reduce<
      Partial<NotificationSettingsSchemaType>
    >(
      (defaults, { emailField, webField, roleIdsField }) => ({
        ...defaults,
        [emailField]:
          (settings as NotificationSettingsSchemaType)[
            emailField as keyof NotificationSettingsSchemaType
          ] ?? false,
        [webField]:
          (settings as NotificationSettingsSchemaType)[
            webField as keyof NotificationSettingsSchemaType
          ] ?? false,
        [roleIdsField]:
          (settings as NotificationSettingsSchemaType)[
            roleIdsField as keyof NotificationSettingsSchemaType
          ] ?? [],
      }),
      {},
    ),
  });

  const mutation = useMutation({
    mutationFn: async (values: NotificationSettingsSchemaType) => {
      const response = await apiFetch(
        '/api/user-management/settings/notifications',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(values),
        },
      );

      if (!response.ok) {
        const { message } = await response.json();
        throw new Error(message);
      }

      return response.json();
    },
    onSuccess: () => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="success">
            <AlertIcon>
              <RiCheckboxCircleFill />
            </AlertIcon>
            <AlertTitle>Settings updated successfully</AlertTitle>
          </Alert>
        ),
        {
          position: 'top-center',
        },
      );

      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
    },
    onError: (error: Error) => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="destructive">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>{error.message}</AlertTitle>
          </Alert>
        ),
        {
          position: 'top-center',
        },
      );
    },
  });

  const handleSubmit = (values: NotificationSettingsSchemaType) => {
    mutation.mutate(values);
  };

  const handleReset = () => {
    form.reset();
  };


  const isProcessing = mutation.status === 'pending';

  // The companies card renders outside the form below (its buttons must not submit
  // it), so it gets its own toast in the same house style.
  const cardToast = (variant: 'success' | 'destructive', message: string) =>
    toast.custom(
      () => (
        <Alert variant="mono" icon={variant}>
          <AlertIcon>
            {variant === 'success' ? <RiCheckboxCircleFill /> : <RiErrorWarningFill />}
          </AlertIcon>
          <AlertTitle>{message}</AlertTitle>
        </Alert>
      ),
      { position: 'top-center' },
    );

  return (
    <div className="space-y-5">
    <form onSubmit={form.handleSubmit(handleSubmit)}>
      <Form {...form}>
        <Card>
          <CardHeader className="border-b border-border">
            <CardTitle>Notification Settings</CardTitle>
          </CardHeader>
          <CardContent className="px-0 py-2.5">
            <Table>
              <TableHeader>
                <TableRow className="text-2sm">
                  <TableHead className="w-[400px] text-muted-foreground ps-6">
                    <div className="inline-flex items-center gap-1.5">
                      <Bell className="text-muted-foreground size-3.5" />
                      Notification
                    </div>
                  </TableHead>
                  <TableHead className="text-muted-foreground">
                    <div className="inline-flex items-center gap-1.5">
                      <Users className="text-muted-foreground size-3.5" />
                      Users
                    </div>
                  </TableHead>
                  <TableHead className="w-36 text-center text-muted-foreground">
                    <div className="inline-flex items-center gap-1.5">
                      <MailWarning className="text-muted-foreground size-3.5" />
                      Email
                    </div>
                  </TableHead>
                  <TableHead className="w-36 text-center text-muted-foreground pe-6">
                    <div className="inline-flex items-center gap-1.5">
                      <AppWindowMac className="text-muted-foreground size-3.5" />
                      Web
                    </div>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {notificationSettings.map(
                  ({
                    label,
                    description,
                    emailField,
                    webField,
                    roleIdsField,
                  }) => (
                    <TableRow key={label}>
                      <TableCell className="ps-6">
                        <div className="space-y-1">
                          <div className="text-md font-semibold">{label}</div>
                          <div className="text-muted-foreground font-2sm font-regular">
                            {description}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <SearchableMultiSelect
                            value={
                              (form.watch(
                                roleIdsField as keyof NotificationSettingsSchemaType,
                              ) as string[]) ?? []
                            }
                            onChange={(next) =>
                              form.setValue(
                                roleIdsField as keyof NotificationSettingsSchemaType,
                                next,
                                { shouldDirty: true },
                              )
                            }
                            emptyMessage="No roles found."
                            className="w-[200px]"
                            // Picked roles render as badges beside this control, so the trigger
                            // stays the compact icon button it has always been.
                            renderTrigger={() => (
                              <Button
                                variant="outline"
                                mode="icon"
                                className="h-7! w-7!"
                                data-testid="notify-roles-trigger"
                                aria-label="Add notify roles"
                              >
                                <UserPlus className="size-3.5!" />
                              </Button>
                            )}
                            options={(roles ?? []).map((role) => ({
                              value: role.id,
                              label: role.name,
                            }))}
                          />
                          <div className="flex items-center flex-wrap gap-2">
                            {(
                              form.watch(
                                roleIdsField as keyof NotificationSettingsSchemaType,
                              ) as string[]
                            )?.length > 0 ? (
                              (
                                form.watch(
                                  roleIdsField as keyof NotificationSettingsSchemaType,
                                ) as string[]
                              ).map((roleId) => {
                                const role = roles.find((r) => r.id === roleId);
                                return (
                                  <Badge key={roleId} variant="secondary">
                                    {role?.name}
                                  </Badge>
                                );
                              })
                            ) : (
                              <span className="text-muted-foreground">
                                Not set
                              </span>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="text-center pe-2!">
                        <FormField
                          control={form.control}
                          name={
                            emailField as keyof NotificationSettingsSchemaType
                          }
                          render={({ field }) => (
                            <FormItem className="items-center">
                              <FormControl>
                                <Checkbox
                                  checked={Boolean(field.value)}
                                  onCheckedChange={field.onChange}
                                />
                              </FormControl>
                            </FormItem>
                          )}
                        />
                      </TableCell>
                      <TableCell className="text-center pe-6!">
                        <FormField
                          control={form.control}
                          name={
                            webField as keyof NotificationSettingsSchemaType
                          }
                          render={({ field }) => (
                            <FormItem className="items-center">
                              <FormControl>
                                <Checkbox
                                  checked={Boolean(field.value)}
                                  onCheckedChange={field.onChange}
                                />
                              </FormControl>
                            </FormItem>
                          )}
                        />
                      </TableCell>
                    </TableRow>
                  ),
                )}
              </TableBody>
            </Table>
          </CardContent>
          <CardFooter className="flex justify-end gap-4 py-5 px-10">
            <Button type="button" variant="outline" onClick={handleReset}>
              Reset
            </Button>
            <Button type="submit" disabled={isProcessing}>
              {isProcessing && <LoaderCircleIcon className="animate-spin" />}
              Save Settings
            </Button>
          </CardFooter>
        </Card>
      </Form>
    </form>
    <DiscontinuedNotifyCompaniesCard toast={cardToast} />
    </div>
  );
};

export default NotificationSettingsPage;
