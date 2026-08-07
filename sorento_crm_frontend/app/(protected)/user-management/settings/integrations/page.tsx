'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { useSettings } from '../components/settings-context';

const IntegrationsSchema = z.object({
  n8nAttachmentWebhookUrl: z.string(),
  n8nCrmChatOutboundWebhookUrl: z.string(),
  n8nStockInquiryReviseWebhookUrl: z.string(),
  googleMapsApiKey: z.string(),
  aiExtractModel: z.string(),
});

type IntegrationsForm = z.infer<typeof IntegrationsSchema>;

export default function IntegrationsSettingsPage() {
  const { settings } = useSettings();
  const queryClient = useQueryClient();

  const form = useForm<IntegrationsForm>({
    resolver: zodResolver(IntegrationsSchema),
    defaultValues: {
      n8nAttachmentWebhookUrl: settings.n8nAttachmentWebhookUrl ?? '',
      n8nCrmChatOutboundWebhookUrl: settings.n8nCrmChatOutboundWebhookUrl ?? '',
      n8nStockInquiryReviseWebhookUrl: settings.n8nStockInquiryReviseWebhookUrl ?? '',
      googleMapsApiKey: settings.googleMapsApiKey ?? '',
      aiExtractModel: settings.aiExtractModel ?? '',
    },
  });

  useEffect(() => {
    form.reset({
      n8nAttachmentWebhookUrl: settings.n8nAttachmentWebhookUrl ?? '',
      n8nCrmChatOutboundWebhookUrl: settings.n8nCrmChatOutboundWebhookUrl ?? '',
      n8nStockInquiryReviseWebhookUrl: settings.n8nStockInquiryReviseWebhookUrl ?? '',
      googleMapsApiKey: settings.googleMapsApiKey ?? '',
      aiExtractModel: settings.aiExtractModel ?? '',
    });
  }, [settings, form]);

  const mutation = useMutation({
    mutationFn: async (values: IntegrationsForm) => {
      const response = await apiFetch('/api/user-management/settings/general', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          n8n_attachment_webhook_url: values.n8nAttachmentWebhookUrl.trim() || null,
          n8n_crm_chat_outbound_webhook_url:
            values.n8nCrmChatOutboundWebhookUrl.trim() || null,
          n8n_stock_inquiry_revise_webhook_url:
            values.n8nStockInquiryReviseWebhookUrl.trim() || null,
          google_maps_api_key: values.googleMapsApiKey.trim() || null,
          ai_extract_model: values.aiExtractModel.trim() || null,
        }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || 'Save failed');
      }
      return response.json();
    },
    onSuccess: () => {
      toast.success('Integration settings saved');
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Integrations</CardTitle>
      </CardHeader>
      <CardContent className="py-8">
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((v) => mutation.mutate(v))}
            className="space-y-6 lg:max-w-[640px] mx-auto"
          >
            <FormField
              control={form.control}
              name="n8nAttachmentWebhookUrl"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Attachment webhook URL</FormLabel>
                  <FormControl>
                    <Input
                      type="url"
                      placeholder="https://…"
                      autoComplete="off"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="n8nCrmChatOutboundWebhookUrl"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>CRM chat outbound webhook URL</FormLabel>
                  <FormControl>
                    <Input
                      type="url"
                      placeholder="https://…"
                      autoComplete="off"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="n8nStockInquiryReviseWebhookUrl"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Stock inquiry revise webhook URL</FormLabel>
                  <FormControl>
                    <Input
                      type="url"
                      placeholder="https://…"
                      autoComplete="off"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="googleMapsApiKey"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Google Maps browser key</FormLabel>
                  <FormControl>
                    <Input placeholder="AIza…" autoComplete="off" {...field} />
                  </FormControl>
                  {/* Shown in plain text on purpose. A Maps JavaScript key is delivered
                      to every page that draws a map, so it cannot be secret - masking it
                      here would imply a protection that does not exist and would stop an
                      admin checking which key is in force. Restrict it in Google Cloud
                      (HTTP referrers + Maps JavaScript / Places / Geocoding only), which
                      is the control that actually works. */}
                  <p className="text-xs text-muted-foreground">
                    Draws the map on the consumer &ldquo;report a problem&rdquo; journey. This key
                    is public by design - restrict it in Google Cloud by HTTP referrer and
                    API. Leave blank to fall back to typed address fields with no map.
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="aiExtractModel"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Receipt extraction model</FormLabel>
                  <FormControl>
                    <Input placeholder="gpt-4o" autoComplete="off" {...field} />
                  </FormControl>
                  <p className="text-xs text-muted-foreground">
                    Reads receipts on the consumer journey. Separate from the AI
                    assistant&rsquo;s model on purpose: OCR of a photographed receipt and
                    assistant chat have different accuracy needs, and a cheaper model
                    misreads digits in dates and product codes. Blank uses gpt-4o.
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? (
                <>
                  <LoaderCircleIcon className="size-4 animate-spin mr-2" />
                  Saving…
                </>
              ) : (
                'Save'
              )}
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
