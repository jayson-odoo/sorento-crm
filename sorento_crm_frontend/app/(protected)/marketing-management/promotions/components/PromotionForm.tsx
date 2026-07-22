'use client';

import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useCreatePromotion, useUpdatePromotion, usePromotion, usePromotions } from '../hooks/usePromotions';
import { PromotionSchema, type PromotionSchemaType } from '../forms/promotion-schema';
import type { PromotionFormData } from '../types/promotion.types';
import PromotionAttachmentsTab from './PromotionAttachmentsTab';
import RecordNavigation from '@/components/common/RecordNavigation';
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';
import { malaysiaCivilYyyyMmDdFromApi, todayMalaysiaYyyyMmDd } from '@/lib/helpers';

interface PromotionFormProps {
  promotionId?: string;
  onSuccess?: () => void;
}

export default function PromotionForm({ promotionId, onSuccess }: PromotionFormProps) {
  const router = useRouter();
  const isEditMode = !!promotionId;
  const { data: promotion, isLoading: isLoadingPromotion } = usePromotion(promotionId || null);
  const createMutation = useCreatePromotion();
  const updateMutation = useUpdatePromotion();
  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
    }),
    [],
  );
  const { data: navigationData } = usePromotions(navigationParams);
  const navigationItems = navigationData?.data ?? [];
  const { data: accessTypeOptions = [] } = useContactAccessTypes();
  const defaultAccessLevels = accessTypeOptions.length > 0 ? accessTypeOptions.map((o) => o.code) : ['dealer', 'end_user'];

  const todayYmd = useMemo(() => todayMalaysiaYyyyMmDd(), []);

  const form = useForm<PromotionSchemaType>({
    resolver: zodResolver(PromotionSchema),
    defaultValues: {
      description: '',
      start_date: todayYmd,
      end_date: todayYmd,
      is_active: true,
      access_levels: defaultAccessLevels,
    },
    mode: 'onSubmit',
  });

  // Track if form has been initialized to prevent multiple resets
  const [formInitialized, setFormInitialized] = useState(false);

  // Load promotion data when editing
  useEffect(() => {
    if (promotion && isEditMode && !formInitialized) {
      // Use setTimeout to ensure SelectContent items are rendered before form reset
      // This is especially important when navigating from list view
      const timeoutId = setTimeout(() => {
        const startYmd = malaysiaCivilYyyyMmDdFromApi(promotion.start_date) ?? todayYmd;
        const endYmd = malaysiaCivilYyyyMmDdFromApi(promotion.end_date) ?? todayYmd;
        form.reset({
          description: promotion.description || '',
          start_date: startYmd,
          end_date: endYmd,
          is_active: promotion.is_active,
          access_levels:
            promotion.access_levels && promotion.access_levels.length > 0
              ? promotion.access_levels
              : defaultAccessLevels,
        });
        setFormInitialized(true);
      }, 0);

      return () => clearTimeout(timeoutId);
    }
  }, [promotion, isEditMode, form, formInitialized, todayYmd]);

  // Reset formInitialized when promotionId changes
  useEffect(() => {
    setFormInitialized(false);
  }, [promotionId]);

  const onSubmit = async (data: PromotionSchemaType) => {
    try {
      // Transform data to ensure proper format
      const formData: PromotionFormData = {
        description: data.description || undefined,
        start_date: data.start_date,
        end_date: data.end_date,
        is_active: data.is_active,
        access_levels: data.access_levels,
      };

      if (isEditMode && promotionId) {
        await updateMutation.mutateAsync({ id: promotionId, data: formData });
      } else {
        await createMutation.mutateAsync(formData);
      }

      if (onSuccess) {
        onSuccess();
      } else {
        router.push('/marketing-management/promotions');
      }
    } catch (error) {
      // Error is handled by the mutation hook
      console.error('Promotion form submission error:', error);
    }
  };

  if (isEditMode && isLoadingPromotion) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderCircleIcon className="size-6 animate-spin" />
      </div>
    );
  }

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        {isEditMode && promotionId && (
          <div className="flex justify-end">
            <RecordNavigation
              currentId={promotionId}
              items={navigationItems}
              basePath="/marketing-management/promotions"
            />
          </div>
        )}
        <Tabs defaultValue="basic" className="w-full">
          <TabsList>
            <TabsTrigger value="basic">Basic Information</TabsTrigger>
            {isEditMode && (
              <TabsTrigger value="attachments">Attachments</TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="basic">
            <Card>
              <CardHeader>
                <CardTitle>{isEditMode ? 'Edit Promotion' : 'Create Promotion'}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
            <FormField
              control={form.control}
              name="access_levels"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Access Levels *</FormLabel>
                  <FormDescription>
                    Choose who can view this promotion.
                  </FormDescription>
                  <div className="mt-2 flex flex-wrap gap-4">
                    {accessTypeOptions.map((opt) => {
                      const checked = field.value?.includes(opt.code);
                      return (
                        <label key={opt.code} className="flex items-center gap-2 text-sm">
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(value) => {
                              const next = new Set(field.value || []);
                              if (value) {
                                next.add(opt.code);
                              } else {
                                next.delete(opt.code);
                              }
                              field.onChange(Array.from(next));
                            }}
                          />
                          {opt.name || opt.code}
                        </label>
                      );
                    })}
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description *</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Enter promotion description..."
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="start_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Start Date *</FormLabel>
                    <FormControl>
                      <Input
                        type="date"
                        name={field.name}
                        ref={field.ref}
                        onBlur={field.onBlur}
                        value={field.value}
                        onChange={(e) => field.onChange(e.target.value)}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="end_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>End Date *</FormLabel>
                    <FormControl>
                      <Input
                        type="date"
                        name={field.name}
                        ref={field.ref}
                        onBlur={field.onBlur}
                        value={field.value}
                        onChange={(e) => field.onChange(e.target.value)}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="is_active"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Active Status</FormLabel>
                    <FormDescription>
                      Enable or disable this promotion
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

                <div className="flex justify-end gap-4 pt-4">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      if (onSuccess) {
                        onSuccess();
                      } else {
                        router.push('/marketing-management/promotions');
                      }
                    }}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={isLoading}>
                    {isLoading ? (
                      <>
                        <LoaderCircleIcon className="size-4 animate-spin" />
                        Saving...
                      </>
                    ) : (
                      <>
                        <Save className="size-4" />
                        {isEditMode ? 'Update Promotion' : 'Create Promotion'}
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {isEditMode && (
            <TabsContent value="attachments">
              <PromotionAttachmentsTab promotionId={promotionId} isEditMode={true} />
            </TabsContent>
          )}
        </Tabs>
      </form>
    </Form>
  );
}
