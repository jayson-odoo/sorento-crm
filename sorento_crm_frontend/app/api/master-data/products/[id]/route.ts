import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma product to frontend expected format (snake_case)
 */
function transformProduct(product: any) {
  return {
    id: product.id,
    product_code: product.productCode,
    product_name: product.productName,
    description: product.description,
    category_id: product.categoryId,
    brand_id: product.brandId,
    base_uom_id: product.baseUomId,
    item_type: product.itemType,
    list_price: Number(product.listPrice),
    cost_price: product.costPrice ? Number(product.costPrice) : null,
    invoice_price: product.invoicePrice ? Number(product.invoicePrice) : null,
    weight: product.weight ? Number(product.weight) : null,
    dimensions_length: product.dimensionsLength ? Number(product.dimensionsLength) : null,
    dimensions_width: product.dimensionsWidth ? Number(product.dimensionsWidth) : null,
    dimensions_height: product.dimensionsHeight ? Number(product.dimensionsHeight) : null,
    warranty_months: product.warrantyMonths,
    has_serial_tracking: product.hasSerialTracking,
    has_batch_tracking: product.hasBatchTracking,
    reorder_level: product.reorderLevel,
    reorder_quantity: product.reorderQuantity,
    is_active: product.isActive,
    created_at: product.createdAt,
    updated_at: product.updatedAt,
    created_by: product.createdBy,
    updated_by: product.updatedBy,
    category: product.category ? {
      id: product.category.id,
      category_code: product.category.categoryCode,
      category_name: product.category.categoryName,
    } : undefined,
    brand: product.brand ? {
      id: product.brand.id,
      brand_code: product.brand.brandCode,
      brand_name: product.brand.brandName,
    } : undefined,
    base_uom: product.baseUom ? {
      id: product.baseUom.id,
      uom_code: product.baseUom.uomCode,
      uom_name: product.baseUom.uomName,
    } : undefined,
  };
}

/**
 * GET /api/master-data/products/:id
 * 
 * Fetch a single product by ID
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid product ID format' },
        { status: 400 },
      );
    }

    const product = await prisma.product.findUnique({
      where: { id },
      include: {
        category: true,
        brand: true,
        baseUom: true,
        productSuppliers: {
          include: {
            supplier: true,
          },
        },
        stockBatches: {
          include: {
            warehouse: true,
          },
        },
        promotionProducts: {
          include: {
            promotion: true,
          },
        },
      },
    });

    if (!product) {
      return NextResponse.json(
        { message: 'Product not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(transformProduct(product));
  } catch (error) {
    console.error('Error fetching product:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * PUT /api/master-data/products/:id
 * 
 * Update a product
 */
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid product ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const product = await prisma.product.update({
      where: { id },
      data: {
        productCode: body.product_code,
        productName: body.product_name,
        description: body.description,
        categoryId: body.category_id,
        brandId: body.brand_id || null,
        baseUomId: body.base_uom_id,
        itemType: body.item_type,
        listPrice: body.list_price,
        costPrice: body.cost_price || null,
        invoicePrice: body.invoice_price || null,
        weight: body.weight || null,
        dimensionsLength: body.dimensions_length || null,
        dimensionsWidth: body.dimensions_width || null,
        dimensionsHeight: body.dimensions_height || null,
        warrantyMonths: body.warranty_months || null,
        hasSerialTracking: body.has_serial_tracking,
        hasBatchTracking: body.has_batch_tracking,
        reorderLevel: body.reorder_level,
        reorderQuantity: body.reorder_quantity,
        isActive: body.is_active,
        updatedBy: session.user?.id || null,
      },
      include: {
        category: true,
        brand: true,
        baseUom: true,
      },
    });

    return NextResponse.json(transformProduct(product));
  } catch (error) {
    console.error('Error updating product:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * DELETE /api/master-data/products/:id
 * 
 * Delete (soft delete) a product
 */
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid product ID format' },
        { status: 400 },
      );
    }

    // Products don't support soft delete, so we deactivate instead
    await prisma.product.update({
      where: { id },
      data: {
        isActive: false,
      },
    });

    return NextResponse.json({ message: 'Product deactivated successfully' });
  } catch (error) {
    console.error('Error deleting product:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
