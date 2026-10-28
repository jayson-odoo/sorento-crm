'use client';

import { PriceTagRequestList } from '@/app/(auth)/portal/components/PriceTagRequestList';
import { MySlug } from '../MySlug';

export default function MyRequestsPriceTagListPage() {
  return <MySlug>{(slug) => <PriceTagRequestList slug={slug} />}</MySlug>;
}
