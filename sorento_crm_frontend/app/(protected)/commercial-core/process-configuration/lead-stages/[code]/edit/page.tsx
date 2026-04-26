'use client';

import { use, useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  useLeadStageByCode,
  useUpdateLeadStageByCode,
} from '@/app/(protected)/commercial/leads/hooks/useLeadStages';
import { LeadStageSchema, type LeadStageSchemaType } from '../../../forms/lead-stage-schema';

export default function EditLeadStagePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const stageCode = decodeURIComponent(code);
  const router = useRouter();
  const { data: row, isLoading } = useLeadStageByCode(stageCode);
  const updateMut = useUpdateLeadStageByCode();
  const [ready, setReady] = useState(false);

  const form = useForm<LeadStageSchemaType>({
    resolver: zodResolver(LeadStageSchema),
    defaultValues: {
      stage_code: stageCode,
      stage_name: '',
      sort_order: 0,
      is_terminal: false,
      allows_conversion: false,
    },
  });

  useEffect(() => {
    if (!row) return;
    form.reset({
      stage_code: row.stage_code,
      stage_name: row.stage_name,
      sort_order: row.sort_order,
      is_terminal: row.is_terminal,
      allows_conversion: row.allows_conversion,
    });
    setReady(true);
  }, [row, form]);

  const onSubmit = async (v: LeadStageSchemaType) => {
    const { stage_code, ...rest } = v;
    void stage_code;
    await updateMut.mutateAsync({ stageCode, data: rest });
    router.push('/commercial-core/process-configuration/lead-stages');
  };

  if (isLoading || !ready) {
    return <LoaderCircleIcon className="mx-auto size-8 animate-spin text-muted-foreground" />;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Edit lead stage</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="max-w-lg space-y-4">
            <FormField
              control={form.control}
              name="stage_code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Code</FormLabel>
                  <FormControl>
                    <Input {...field} disabled />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="stage_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="sort_order"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Sort order</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 0)}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="is_terminal"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-md border p-3">
                  <FormLabel>Terminal</FormLabel>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="allows_conversion"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-md border p-3">
                  <FormLabel>Allows conversion</FormLabel>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            <div className="flex gap-2">
              <Button type="submit" disabled={updateMut.isPending}>
                <Save className="size-4" />
                Save
              </Button>
              <Button variant="outline" asChild>
                <Link href="/commercial-core/process-configuration/lead-stages">Cancel</Link>
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
