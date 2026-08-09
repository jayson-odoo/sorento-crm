'use client';

import { useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { CertificateSchema } from '../forms/certificate-schema';
import { useCertificate, useCreateCertificate, useUpdateCertificate } from '../hooks/useCertificates';
import { STATUS_LABELS } from '../lib/certificateDisplay';
import type { CertificateFormData } from '../types/certificate.types';

interface CertificateFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  certificateId?: string;
}

const EMPTY = {
  scheme: '',
  certifying_body: '',
  certificate_number: '',
  issuer: '',
  title: '',
  status: 'active' as const,
  issued_at: '',
  valid_from: '',
  valid_until: '',
};

export default function CertificateFormDialog({
  open,
  onOpenChange,
  certificateId,
}: CertificateFormDialogProps) {
  const { data: certificate } = useCertificate(open && certificateId ? certificateId : null);
  const createMutation = useCreateCertificate();
  const updateMutation = useUpdateCertificate();

  const form = useForm<z.infer<typeof CertificateSchema>>({
    resolver: zodResolver(CertificateSchema),
    defaultValues: EMPTY,
  });

  useEffect(() => {
    if (!open) return;
    if (certificateId && certificate) {
      form.reset({
        scheme: certificate.scheme,
        certifying_body: certificate.certifying_body,
        certificate_number: certificate.certificate_number,
        issuer: certificate.issuer ?? '',
        title: certificate.title ?? '',
        status: certificate.status,
        issued_at: certificate.current_revision?.issued_at ?? '',
        valid_from: certificate.current_revision?.valid_from ?? '',
        valid_until: certificate.current_revision?.valid_until ?? '',
      });
    } else {
      form.reset(EMPTY);
    }
  }, [open, form, certificateId, certificate]);

  const onSubmit = async (data: z.infer<typeof CertificateSchema>) => {
    try {
      const payload: CertificateFormData = {
        scheme: data.scheme.trim(),
        certifying_body: data.certifying_body.trim(),
        certificate_number: data.certificate_number.trim(),
        issuer: data.issuer ? data.issuer : null,
        title: data.title ? data.title : null,
        status: data.status,
        issued_at: data.issued_at ? data.issued_at : null,
        valid_from: data.valid_from ? data.valid_from : null,
        valid_until: data.valid_until ? data.valid_until : null,
      };
      if (certificateId) {
        await updateMutation.mutateAsync({ id: certificateId, data: payload });
      } else {
        await createMutation.mutateAsync(payload);
      }
      onOpenChange(false);
      form.reset(EMPTY);
    } catch {
      // Error surfaced by the mutation's onError toast.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{certificateId ? 'Edit Certificate' : 'Add Certificate'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="scheme"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Scheme *</FormLabel>
                    <FormControl>
                      <Input placeholder="PPS" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="certificate_number"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Certificate number *</FormLabel>
                    <FormControl>
                      <Input placeholder="04424FC" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="certifying_body"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Certifying body *</FormLabel>
                  <FormControl>
                    <Input placeholder="IKRAM" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="issuer"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Issuer</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="IKRAM QA Services Sdn Bhd"
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Title</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Product Certification Scheme - sanitary ware"
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <FormField
                control={form.control}
                name="issued_at"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Issued on</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} value={field.value || ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="valid_from"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Valid from</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} value={field.value || ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="valid_until"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Valid until</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} value={field.value || ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="status"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Status *</FormLabel>
                  <FormControl>
                    <SearchableSelect
                      value={field.value}
                      onChange={(value) => field.onChange(value)}
                      options={[
                        { value: 'active', label: STATUS_LABELS.active },
                        { value: 'archived', label: STATUS_LABELS.archived },
                      ]}
                      placeholder="Select status"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={createMutation.isPending || updateMutation.isPending}
              >
                {certificateId ? 'Update' : 'Create'}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
