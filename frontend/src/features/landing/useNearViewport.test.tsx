import { act, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { useNearViewport } from './useNearViewport';

function Preview() {
  const { ref, visible } = useNearViewport();
  return <div ref={ref}>{visible ? 'Ready' : 'Deferred'}</div>;
}

afterEach(() => vi.unstubAllGlobals());

it('defers offscreen content, activates near the viewport, and cleans up the observer', () => {
  let notify: IntersectionObserverCallback;
  const observe = vi.fn();
  const disconnect = vi.fn();
  vi.stubGlobal(
    'IntersectionObserver',
    vi.fn(function (callback: IntersectionObserverCallback) {
      notify = callback;
      return { observe, disconnect };
    }),
  );
  const { unmount } = render(<Preview />);
  expect(observe).toHaveBeenCalledWith(screen.getByText('Deferred'));
  const intersect = (isIntersecting: boolean) =>
    act(() =>
      notify([{ isIntersecting } as IntersectionObserverEntry], {} as IntersectionObserver),
    );
  intersect(false);
  expect(screen.getByText('Deferred')).toBeInTheDocument();
  intersect(true);
  expect(screen.getByText('Ready')).toBeInTheDocument();
  expect(disconnect).toHaveBeenCalledOnce();
  unmount();
  expect(disconnect).toHaveBeenCalledTimes(2);
});

it('shows content if the browser does not support IntersectionObserver', () => {
  const observer = window.IntersectionObserver;
  // Deleting the property exercises the same capability check as old browsers.
  Reflect.deleteProperty(window, 'IntersectionObserver');
  try {
    render(<Preview />);
    expect(screen.getByText('Ready')).toBeInTheDocument();
  } finally {
    if (observer) window.IntersectionObserver = observer;
  }
});
