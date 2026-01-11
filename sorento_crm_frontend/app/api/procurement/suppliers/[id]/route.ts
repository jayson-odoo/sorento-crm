import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

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
        { message: 'Invalid supplier ID format' },
        { status: 400 },
      );
    }

    const supplier = await prisma.supplier.findUnique({
      where: { id },
    });

    if (!supplier) {
      return NextResponse.json(
        { message: 'Supplier not found' },
        { status: 404 },
      );
    }

    // Transform Prisma supplier to frontend expected format (snake_case)
    const transformedSupplier = {
      id: supplier.id,
      supplier_code: supplier.supplierCode,
      supplier_name: supplier.supplierName,
      contact_name: supplier.contactName,
      email: supplier.email,
      phone_number: supplier.phoneNumber,
      website: supplier.website,
      address_line1: supplier.addressLine1,
      address_line2: supplier.addressLine2,
      city: supplier.city,
      state: supplier.state,
      postal_code: supplier.postalCode,
      country: supplier.country,
      payment_terms_days: supplier.paymentTermsDays,
      is_active: supplier.isActive,
      created_at: supplier.createdAt,
      updated_at: supplier.updatedAt,
    };

    return NextResponse.json(transformedSupplier);
  } catch (error) {
    console.error('Error fetching supplier:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

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
        { message: 'Invalid supplier ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const supplier = await prisma.supplier.update({
      where: { id },
      data: {
        supplierCode: body.supplier_code,
        supplierName: body.supplier_name,
        contactName: body.contact_name || null,
        email: body.email || null,
        phoneNumber: body.phone_number || null,
        website: body.website || null,
        addressLine1: body.address_line1 || null,
        addressLine2: body.address_line2 || null,
        city: body.city || null,
        state: body.state || null,
        postalCode: body.postal_code || null,
        country: body.country || null,
        paymentTermsDays: body.payment_terms_days || null,
        isActive: body.is_active,
      },
    });

    // Transform Prisma supplier to frontend expected format (snake_case)
    const transformedSupplier = {
      id: supplier.id,
      supplier_code: supplier.supplierCode,
      supplier_name: supplier.supplierName,
      contact_name: supplier.contactName,
      email: supplier.email,
      phone_number: supplier.phoneNumber,
      website: supplier.website,
      address_line1: supplier.addressLine1,
      address_line2: supplier.addressLine2,
      city: supplier.city,
      state: supplier.state,
      postal_code: supplier.postalCode,
      country: supplier.country,
      payment_terms_days: supplier.paymentTermsDays,
      is_active: supplier.isActive,
      created_at: supplier.createdAt,
      updated_at: supplier.updatedAt,
    };

    return NextResponse.json(transformedSupplier);
  } catch (error) {
    console.error('Error updating supplier:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

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
        { message: 'Invalid supplier ID format' },
        { status: 400 },
      );
    }

    await prisma.supplier.update({
      where: { id },
      data: {
        isActive: false,
      },
    });

    return NextResponse.json({ message: 'Supplier deleted successfully' });
  } catch (error) {
    console.error('Error deleting supplier:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
