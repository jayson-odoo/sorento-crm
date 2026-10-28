'use client';

import { PriceTagRequestForm } from '@/app/(auth)/portal/components/PriceTagRequestForm';
import { MySlug } from '../../MySlug';

export default function MyRequestsPriceTagNewPage() {
  return <MySlug>{(slug) => <PriceTagRequestForm slug={slug} />}</MySlug>;
}
