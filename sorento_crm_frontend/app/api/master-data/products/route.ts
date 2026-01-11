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
 * GET /api/master-data/products
 * 
 * Fetch products with pagination, sorting, and filtering
 * 
 * Query params:
 * - page: page number (default: 1)
 * - limit: items per page (default: 50)
 * - sort: field to sort by
 * - dir: sort direction (asc/desc)
 * - query: search query
 * - category_id: filter by category
 * - brand_id: filter by brand
 * - status: filter by status (active/inactive/all)
 * - price_min: minimum price
 * - price_max: maximum price
 * - item_type: filter by item type
 */
export async function GET(req: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { searchParams } = new URL(req.url);
    const page = parseInt(searchParams.get('page') || '1', 10);
    const limit = parseInt(searchParams.get('limit') || '50', 10);
    const query = searchParams.get('query') || '';
    const sortField = searchParams.get('sort') || 'created_at';
    const sortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';
    const categoryId = searchParams.get('category_id') || null;
    const brandId = searchParams.get('brand_id') || null;
    const status = searchParams.get('status') || 'all';
    const priceMin = searchParams.get('price_min');
    const priceMax = searchParams.get('price_max');
    const itemType = searchParams.get('item_type') || null;

    // Build where clause with filters
    const whereClause: any = {
      AND: [
        ...(categoryId && categoryId !== 'all' ? [{ categoryId }] : []),
        ...(brandId && brandId !== 'all' ? [{ brandId }] : []),
        ...(status && status !== 'all' ? [{ isActive: status === 'active' }] : []),
        ...(itemType ? [{ itemType }] : []),
        ...(priceMin || priceMax ? [{
          listPrice: {
            ...(priceMin ? { gte: parseFloat(priceMin) } : {}),
            ...(priceMax ? { lte: parseFloat(priceMax) } : {}),
          }
        }] : []),
        ...(query ? [{
          OR: [
            { productCode: { contains: query, mode: 'insensitive' } },
            { productName: { contains: query, mode: 'insensitive' } },
          ],
        }] : []),
      ],
    };

    // Map sort field to Prisma field names
    const sortMap: Record<string, any> = {
      'created_at': 'createdAt',
      'product_code': 'productCode',
      'product_name': 'productName',
      'list_price': 'listPrice',
      'is_active': 'isActive',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const totalCount = await prisma.product.count({ where: whereClause });

    // Fetch products with filters
    const products = await prisma.product.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      orderBy: { [mappedSortField]: sortDirection },
      include: {
        category: {
          select: {
            id: true,
            categoryName: true,
            categoryCode: true,
          },
        },
        brand: {
          select: {
            id: true,
            brandName: true,
            brandCode: true,
          },
        },
        baseUom: {
          select: {
            id: true,
            uomName: true,
            uomCode: true,
          },
        },
      },
    });

    // Transform Prisma response to match frontend expected format (snake_case)
    const transformedProducts = products.map(transformProduct);

    return NextResponse.json({
      data: transformedProducts,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching products:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * POST /api/master-data/products
 * 
 * Create a new product
 */
export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const body = await request.json();

    const product = await prisma.product.create({
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
        hasSerialTracking: body.has_serial_tracking || false,
        hasBatchTracking: body.has_batch_tracking || false,
        reorderLevel: body.reorder_level || 10,
        reorderQuantity: body.reorder_quantity || 50,
        isActive: body.is_active !== false,
        createdBy: session.user?.id || null,
      },
      include: {
        category: true,
        brand: true,
        baseUom: true,
      },
    });

    return NextResponse.json(transformProduct(product), { status: 201 });
  } catch (error) {
    console.error('Error creating product:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
