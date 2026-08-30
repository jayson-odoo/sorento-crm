'use client';

import { useEffect } from 'react';
import { useParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import DetailActions from '@/components/common/DetailActions';
import BackToList from '@/components/common/BackToList';
import {
  integrationLogsPagerQuery,
  useIntegrationLog,
  useRetryIntegrationLog,
} from '../hooks/useIntegrationLogs';
import { RefreshCw } from 'lucide-react';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { toast } from 'sonner';
import { useForm } from 'react-hook-form';

const formatJsonPayload = (payload?: string | null) => {
  if (!payload) return '';
  try {
    return JSON.stringify(JSON.parse(payload), null, 2);
  } catch {
    return payload;
  }
};

export default function IntegrationLogDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const { data: log, isLoading } = useIntegrationLog(id);
  const retryMutation = useRetryIntegrationLog();

  const form = useForm({
    defaultValues: {
      id: '',
      status: '',
      integration_channel: '',
      business_table: '',
      business_id: '',
      external_reference: '',
      direction: '',
      endpoint: '',
      http_method: '',
      status_code: '',
      retry_count: '',
      max_retry_allowed: '',
      correlation_id: '',
      created_at: '',
      created_by: '',
      processed_at: '',
      updated_at: '',
      next_retry_at: '',
      request_headers: '',
      request_payload: '',
      response_headers: '',
      response_payload: '',
      error_code: '',
      error_message: '',
    },
  });

  // Update form values when log data is loaded
  useEffect(() => {
    if (log && !isLoading) {
      form.reset({
      id: log.id || '',
      status: log.status || '',
      integration_channel: log.integration_channel || '',
      business_table: log.business_table || '',
      business_id: log.business_id || '',
      external_reference: log.external_reference || '',
      direction: log.direction || '',
      endpoint: log.endpoint || '',
      http_method: log.http_method || '',
      status_code: log.status_code?.toString() || '',
      retry_count: `${log.retry_count || 0}`,
      max_retry_allowed: `${log.max_retry_allowed || 0}`,
      correlation_id: log.correlation_id || '',
      created_at: log.created_at ? formatDateTimeInMalaysia(log.created_at) : '',
      created_by: log.created_by || '',
      processed_at: log.processed_at ? formatDateTimeInMalaysia(log.processed_at) : '',
      updated_at: log.updated_at ? formatDateTimeInMalaysia(log.updated_at) : '',
      next_retry_at: log.next_retry_at ? formatDateTimeInMalaysia(log.next_retry_at) : '',
      request_headers: log.request_headers || '',
      request_payload: formatJsonPayload(log.request_payload),
      response_headers: log.response_headers || '',
      response_payload: formatJsonPayload(log.response_payload),
      error_code: log.error_code || '',
      error_message: log.error_message || '',
      });
    }
  }, [log, isLoading, form]);

  if (isLoading) {
    return (
      <div className="container py-6 space-y-6">
        <Skeleton className="h-12 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!log) {
    return (
      <div className="container py-6">
        <p>Integration log not found</p>
      </div>
    );
  }

  const statusVariants: Record<string, 'destructive' | 'warning' | 'success' | 'secondary' | 'info'> = {
    failed: 'destructive',
    pending: 'warning',
    processing: 'secondary',
    sent: 'info',
    success: 'success',
  };
  const status = (log.status || 'pending') as string;
  const statusKey = status.toLowerCase();

  return (
    <>
      <Container>
        <PageHeader
          title="Integration Log Details"
          actions={
            <BackToList
              listPath="/integration-management/integration-logs"
              label="Back to integration logs"
            />
          }
        />

        {/* The record's own actions: pager, gear, primary (D6). They sit under the
            toolbar rather than on it, and wrap at 375. */}
        <DetailActions
          className="mb-4"
          pager={{
            ...integrationLogsPagerQuery,
            detailPath: '/integration-management/integration-logs',
            currentId: id,
            ariaLabel: 'integration log',
          }}
          primary={
            log.status === 'failed' && log.retry_count < log.max_retry_allowed ? (
              <Button
                onClick={() => {
                  retryMutation.mutate(log.id, {
                    onSuccess: () => {
                      toast.success('Retry initiated');
                    },
                    onError: (error: Error) => {
                      toast.error(error.message || 'Failed to retry');
                    },
                  });
                }}
                disabled={retryMutation.isPending}
              >
                <RefreshCw className="size-4 mr-2" />
                Retry
              </Button>
            ) : null
          }
        />
      </Container>

      <Container>

      <Form {...form}>
        <form className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Basic Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <FormField
                  control={form.control}
                  name="id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>ID</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly className="font-mono text-sm" />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="status"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Status</FormLabel>
                      <FormControl>
                        <div className="pt-2">
                          <Badge
                            variant={statusVariants[statusKey] || 'secondary'}
                            appearance="light"
                            shape="circle"
                            size="md"
                            className="rounded-full font-medium"
                          >
                            {status.charAt(0).toUpperCase() + status.slice(1)}
                          </Badge>
                        </div>
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="integration_channel"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Integration Channel</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="business_table"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Business Table</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="business_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Business ID</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly className="font-mono text-sm" />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="external_reference"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>External Reference</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly placeholder="-" />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="direction"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Direction</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="correlation_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Correlation ID</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly placeholder="-" className="font-mono text-sm" />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Request Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <FormField
                  control={form.control}
                  name="endpoint"
                  render={({ field }) => (
                    <FormItem className="md:col-span-2">
                      <FormLabel>Endpoint</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly className="break-all" />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="http_method"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>HTTP Method</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="status_code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Status Code</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly placeholder="-" />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="retry_count"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Retry Count</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="max_retry_allowed"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Max Retry Allowed</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="created_at"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Created At</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="processed_at"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Processed At</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly placeholder="-" />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="next_retry_at"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Next Retry At</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly placeholder="-" />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="created_by"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Created By</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly placeholder="-" />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="updated_at"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Updated At</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </div>
            </CardContent>
          </Card>

          {log.request_headers && (
            <Card>
              <CardHeader>
                <CardTitle>Request Headers</CardTitle>
              </CardHeader>
              <CardContent>
                <FormField
                  control={form.control}
                  name="request_headers"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Textarea
                          {...field}
                          readOnly
                          className="font-mono text-xs min-h-[100px]"
                          placeholder="-"
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          )}

          {log.request_payload && (
            <Card>
              <CardHeader>
                <CardTitle>Request Payload</CardTitle>
              </CardHeader>
              <CardContent>
                <FormField
                  control={form.control}
                  name="request_payload"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Textarea
                          {...field}
                          readOnly
                          className="font-mono text-xs min-h-[200px]"
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          )}

          {log.response_headers && (
            <Card>
              <CardHeader>
                <CardTitle>Response Headers</CardTitle>
              </CardHeader>
              <CardContent>
                <FormField
                  control={form.control}
                  name="response_headers"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Textarea
                          {...field}
                          readOnly
                          className="font-mono text-xs min-h-[100px]"
                          placeholder="-"
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          )}

          {log.response_payload && (
            <Card>
              <CardHeader>
                <CardTitle>Response Payload</CardTitle>
              </CardHeader>
              <CardContent>
                <FormField
                  control={form.control}
                  name="response_payload"
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Textarea
                          {...field}
                          readOnly
                          className="font-mono text-xs min-h-[200px]"
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          )}

          {(log.error_code || log.error_message) && (
            <Card>
              <CardHeader>
                <CardTitle>Error Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="error_code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Error Code</FormLabel>
                      <FormControl>
                        <Input {...field} readOnly className="text-destructive" placeholder="-" />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="error_message"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Error Message</FormLabel>
                      <FormControl>
                        <Textarea
                          {...field}
                          readOnly
                          className="text-destructive min-h-[100px]"
                          placeholder="-"
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          )}
        </form>
      </Form>
      </Container>
    </>
  );
}
