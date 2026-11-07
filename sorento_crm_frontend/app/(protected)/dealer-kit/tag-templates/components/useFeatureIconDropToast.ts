'use client';

/**
 * Feature icons that stop fitting their box (crew pass, 5 Nov): a warning toast the moment a
 * change (preview product, icon size, spacing, box resize) makes more icons drop than before, the
 * same `toast.warning` the editor uses for layers left outside a resized tag. Only on an increase,
 * so a steady state or an improvement says nothing, and a template that opens already dropping
 * icons is left to the inspector's own warning.
 */
import { useEffect, useRef } from 'react';
import { toast } from '@/lib/toast';

export function featureIconDropToastText(dropped: number): string {
  return dropped === 1
    ? '1 feature icon does not fit its box and will not print. Widen the box or make the icons smaller.'
    : `${dropped} feature icons do not fit their box and will not print. Widen the box or make the icons smaller.`;
}

/** `dropped`: how many feature icons the canvas cannot draw right now, across its layers. */
export function useFeatureIconDropToast(dropped: number): void {
  const previous = useRef(dropped);
  useEffect(() => {
    if (dropped > previous.current) toast.warning(featureIconDropToastText(dropped));
    previous.current = dropped;
  }, [dropped]);
}

/** PRICETAG-ACCESSORIES (A6): the same warning for accessories that stop fitting their box. */
export function accessoryDropToastText(dropped: number): string {
  return dropped === 1
    ? '1 accessory does not fit its box and will not print. Make the box bigger or the cards smaller.'
    : `${dropped} accessories do not fit their box and will not print. Make the box bigger or the cards smaller.`;
}

/** `dropped`: how many accessories the canvas cannot draw right now, across its boxes. */
export function useAccessoryDropToast(dropped: number): void {
  const previous = useRef(dropped);
  useEffect(() => {
    if (dropped > previous.current) toast.warning(accessoryDropToastText(dropped));
    previous.current = dropped;
  }, [dropped]);
}
