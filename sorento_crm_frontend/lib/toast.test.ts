import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('sonner', () => {
  const fn = vi.fn() as any;
  fn.success = vi.fn();
  fn.error = vi.fn();
  fn.info = vi.fn();
  fn.warning = vi.fn();
  fn.message = vi.fn();
  fn.promise = vi.fn();
  fn.dismiss = vi.fn();
  fn.loading = vi.fn();
  fn.custom = vi.fn();
  fn.getHistory = vi.fn();
  fn.getToasts = vi.fn();
  return { toast: fn };
});

import { toast as sonnerToast } from 'sonner';
import { toast } from './toast';

describe('lib/toast (M6-04)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('toast.success defaults to a 4000ms duration', () => {
    toast.success('Saved');
    expect(sonnerToast.success).toHaveBeenCalledWith('Saved', { duration: 4000 });
  });

  it('toast.error defaults to Infinity with a close button', () => {
    toast.error('Failed');
    expect(sonnerToast.error).toHaveBeenCalledWith('Failed', {
      duration: Infinity,
      closeButton: true,
    });
  });

  it('a caller-supplied duration overrides the default', () => {
    toast.error('Failed', { duration: 10_000 });
    expect(sonnerToast.error).toHaveBeenCalledWith('Failed', {
      duration: 10_000,
      closeButton: true,
    });
  });

  it('passes through info/warning/promise/dismiss/custom/loading unchanged', () => {
    toast.info('info');
    toast.warning('warn');
    toast.dismiss('id-1');
    toast.loading('loading');
    const jsx = () => null as any;
    toast.custom(jsx);
    const promise = Promise.resolve('x');
    toast.promise(promise, { loading: 'l', success: 's', error: 'e' });

    expect(sonnerToast.info).toHaveBeenCalledWith('info');
    expect(sonnerToast.warning).toHaveBeenCalledWith('warn');
    expect(sonnerToast.dismiss).toHaveBeenCalledWith('id-1');
    expect(sonnerToast.loading).toHaveBeenCalledWith('loading');
    expect(sonnerToast.custom).toHaveBeenCalledWith(jsx);
    expect(sonnerToast.promise).toHaveBeenCalledWith(promise, {
      loading: 'l',
      success: 's',
      error: 'e',
    });
  });

  it('the bare toast(...) call passes straight through', () => {
    toast('plain message', { id: 'x' });
    expect(sonnerToast).toHaveBeenCalledWith('plain message', { id: 'x' });
  });
});
