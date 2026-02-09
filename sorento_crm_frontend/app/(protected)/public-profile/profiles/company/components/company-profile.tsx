'use client';

import Link from 'next/link';
import dynamic from 'next/dynamic';
import {
  RemixiconComponentType,
  RiFacebookCircleLine,
  RiWhatsappLine,
  RiYoutubeLine,
} from '@remixicon/react';
import { Dribbble, LucideIcon, MapPinHouse } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

// Dynamically import the map component with SSR disabled
const CompanyMap = dynamic(() => import('./company-map').then((mod) => mod.CompanyMap), { ssr: false });

interface IProfileRow {
  icon: LucideIcon | RemixiconComponentType;
  text: string;
  info: boolean;
}
type IProfileRows = Array<IProfileRow>;

interface IProfileProduct {
  label: string;
}
type IProfileProducts = Array<IProfileProduct>;

const CompanyProfile = () => {
// #region agent log
typeof window !== 'undefined' && fetch('http://127.0.0.1:7242/ingest/82ff2983-30f8-41d1-a335-d37b94435673',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'company-profile.tsx:31',message:'CompanyProfile render start',data:{windowDefined:typeof window!=='undefined',hasCompanyMap:!!CompanyMap},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H2'})}).catch(()=>{});
// #endregion
  const rows: IProfileRows = [
    {
      icon: Dribbble,
      text: 'https://duolingo.com',
      info: true,
    },
    {
      icon: RiFacebookCircleLine,
      text: 'duolingo',
      info: true,
    },
    {
      icon: RiYoutubeLine,
      text: 'duolingo-tuts',
      info: true,
    },
    {
      icon: RiWhatsappLine,
      text: '(31) 6-1235-4567',
      info: false,
    },
    {
      icon: MapPinHouse,
      text: 'Herengracht 501, 1017 BV Amsterdam, NL',
      info: false,
    },
  ];

  const products: IProfileProducts = [
    { label: 'Lingo Kids' },
    { label: 'Lingo Express' },
    { label: 'Fun Learning' },
    { label: 'Lingo Espanol' },
    { label: 'Speaking Mastery' },
    { label: 'Grammar Guru' },
    { label: 'Lingo Quest' },
    { label: 'History Lessons' },
    { label: 'Global Explorer' },
    { label: 'Translator' },
    { label: 'Webflow' },
    { label: 'Language Lab' },
    { label: 'Lingo Plus' },
  ];

  const renderRows = (row: IProfileRow, index: number) => {
    return (
      <div key={index} className="flex items-center gap-2.5">
        <span>
          <row.icon className="text-lg text-muted-foreground" size={18} />
        </span>
        {row.info ? (
          <Link href={row.text} className="link text-sm font-medium">
            {row.text}
          </Link>
        ) : (
          <span className="text-sm text-mono">{row.text}</span>
        )}
      </div>
    );
  };

  const renderProducts = (product: IProfileProduct, index: number) => {
    return (
      <Badge key={index} size="lg" variant="secondary">
        {product.label}
      </Badge>
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Company Profile</CardTitle>
      </CardHeader>
      <CardContent>
        <h3 className="text-base font-semibold text-mono leading-none mb-5">
          Headquarter
        </h3>
        <div className="flex flex-wrap items-center gap-5 mb-10">
          <CompanyMap />
          <div className="flex flex-col gap-2.5">
            {rows.map((row, index) => {
              return renderRows(row, index);
            })}
          </div>
        </div>
        <div className="grid gap-2.5 mb-7">
          <div className="text-base font-semibold text-mono">About</div>
          <p className="text-sm text-foreground leading-5.5">
            Now that I’m done thoroughly mangling that vague metaphor, let’s get
            down to business. You know you need to start blogging to grow your
            business, but you don’t know how. In this post, I’ll show you how to
            write a great blog post in five simple steps that people will
            actually want to read.
          </p>
        </div>
        <div className="flex flex-col gap-4 mb-2.5">
          <div className="text-base font-semibold text-mono">Products</div>
          <div className="flex flex-wrap gap-2.5">
            {products.map((product, index) => {
              return renderProducts(product, index);
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export {
  CompanyProfile,
  type IProfileRow,
  type IProfileRows,
  type IProfileProduct,
  type IProfileProducts,
};
