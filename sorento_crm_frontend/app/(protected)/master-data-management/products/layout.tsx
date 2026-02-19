'use client';

/**
 * Products layout. Category, Brand, and UOM are fetched inside ProductForm
 * (same pattern as UOM - consistent behavior when editing products).
 */
export default function ProductsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
