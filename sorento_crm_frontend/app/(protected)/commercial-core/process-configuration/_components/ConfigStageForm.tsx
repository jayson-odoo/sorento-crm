'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  useConfigStageByCode,
  useCreateConfigStage,
  useUpdateConfigStage,
} from '../hooks/useConfigStages';
import { ConfigStageSchema, type ConfigStageSchemaType } from '../forms/config-stage-schema';
import type { ConfigStageResource } from '../services/configStageService';
import type { ConfigStageFormData } from '../types/configStage.types';

type Props = {
  resource: ConfigStageResource;
  stageCode?: string;
  listPath: string;
};

export default function ConfigStageForm({ resource, stageCode, listPath }: Props) {
  const router = useRouter();
  const isEdit = !!stageCode;
  const { data: row, isLoading } = useConfigStageByCode(resource, stageCode ?? null);
  const createMut = useCreateConfigStage(resource);
  const updateMut = useUpdateConfigStage(resource);

  const form = useForm<ConfigStageSchemaType>({
    resolver: zodResolver(ConfigStageSchema),
    defaultValues: {
      stage_code: '',
      stage_name: '',
      description: '',
      sort_order: 0,
      is_terminal: false,
      is_active: true,
    },
    mode: 'onSubmit',
  });

  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    setInitialized(false);
  }, [stageCode]);

  useEffect(() => {
    if (!isEdit || !row || initialized) return;
    const t = setTimeout(() => {
      form.reset({
        stage_code: row.stage_code,
        stage_name: row.stage_name,
        description: row.description || '',
        sort_order: row.sort_order,
        is_terminal: row.is_terminal,
        is_active: row.is_active,
      });
      setInitialized(true);
    }, 0);
    return () => clearTimeout(t);
  }, [row, isEdit, form, initialized]);

  const onSubmit = async (values: ConfigStageSchemaType) => {
    const body: ConfigStageFormData = {
      stage_code: values.stage_code,
      stage_name: values.stage_name,
      description: values.description || undefined,
      sort_order: values.sort_order,
      is_terminal: values.is_terminal,
      is_active: values.is_active,
    };
    if (isEdit && stageCode) {
      const { stage_code: _c, ...rest } = body;
      await updateMut.mutateAsync({ code: stageCode, data: rest });
    } else {
      await createMut.mutateAsync(body);
    }
    router.push(listPath);
  };

  if (isEdit && isLoading) {
    return (
      <Card>
        <CardContent className="flex justify-center py-12">
          <LoaderCircleIcon className="size-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{isEdit ? 'Edit stage' : 'New stage'}</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 max-w-lg">
            <FormField
              control={form.control}
              name="stage_code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Code</FormLabel>
                  <FormControl>
                    <Input {...field} disabled={isEdit} autoComplete="off" />
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
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea {...field} value={field.value || ''} rows={3} />
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
              name="is_active"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                  <FormLabel>Active</FormLabel>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="is_terminal"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                  <FormLabel>Terminal</FormLabel>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />
            <div className="flex gap-2">
              <Button type="submit" disabled={createMut.isPending || updateMut.isPending}>
                {(createMut.isPending || updateMut.isPending) && <LoaderCircleIcon className="size-4 animate-spin" />}
                <Save className="size-4" />
                Save
              </Button>
              <Button type="button" variant="outline" onClick={() => router.push(listPath)}>
                Cancel
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
