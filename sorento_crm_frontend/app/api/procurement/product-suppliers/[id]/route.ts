import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

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

    // TODO: Implement once Prisma models are added
    return NextResponse.json(
      { message: 'Product supplier update endpoint - database tables need to be created first' },
      { status: 501 },
    );
  } catch (error) {
    console.error('Error updating product supplier:', error);
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
        { message: 'Invalid product supplier ID format' },
        { status: 400 },
      );
    }

    // Check if product supplier exists
    const productSupplier = await prisma.productSupplier.findUnique({
      where: { id },
    });

    if (!productSupplier) {
      return NextResponse.json(
        { message: 'Product supplier not found' },
        { status: 404 },
      );
    }

    // Permanently delete the product supplier
    await prisma.productSupplier.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'Product supplier deleted successfully' });
  } catch (error) {
    console.error('Error deleting product supplier:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
