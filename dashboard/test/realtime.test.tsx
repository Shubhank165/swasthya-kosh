/**
 * The socket — 3/3 §11 item 6, §7.
 *
 * Two properties, and both are about being honest when the connection is not
 * working:
 *
 * 1. **A drop then a restore refetches.** It does not replay. A gap in a
 *    message stream is invisible, and a list stitched back together from
 *    whatever arrived after the gap shows a clinical state that never existed.
 * 2. **Connection loss is visible.** A worklist that looks live and is twenty
 *    minutes old is the specific failure this indicator exists to prevent.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useWorklistSocket, worklistSocketUrl } from '../src/lib/realtime';

/** A `WebSocket` a test can open, message and kill by hand. */
class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  closed = false;

  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }

  open() {
    this.onopen?.();
  }

  deliver(frame: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(frame) }));
  }

  drop() {
    this.onclose?.();
  }

  close() {
    this.closed = true;
  }
}

function setup(onChange: () => void) {
  FakeSocket.instances = [];
  const factory = (url: string) => new FakeSocket(url) as unknown as WebSocket;
  const view = renderHook(() =>
    useWorklistSocket({ department: 'kayachikitsa', onChange, socketFactory: factory }),
  );
  return { view, factory };
}

describe('the worklist socket', () => {
  it('scopes the connection to the department', () => {
    expect(worklistSocketUrl('kayachikitsa')).toMatch(/\/ws\/worklist\?department=kayachikitsa$/);
    expect(worklistSocketUrl(null)).toMatch(/\/ws\/worklist$/);
  });

  it('reports live once connected', async () => {
    const { view } = setup(vi.fn());
    expect(view.result.current.status).toBe('connecting');
    act(() => FakeSocket.instances[0]!.open());
    await waitFor(() => expect(view.result.current.status).toBe('live'));
  });

  it('refetches when an event that changes the worklist arrives', async () => {
    const onChange = vi.fn();
    setup(onChange);
    act(() => FakeSocket.instances[0]!.open());
    act(() => FakeSocket.instances[0]!.deliver({ event: 'intake.received', intake_id: 'i-1' }));
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
  });

  it('ignores heartbeats and the subscription acknowledgement', async () => {
    const onChange = vi.fn();
    setup(onChange);
    act(() => FakeSocket.instances[0]!.open());
    act(() => {
      FakeSocket.instances[0]!.deliver({ event: 'heartbeat' });
      FakeSocket.instances[0]!.deliver({ event: 'subscribed', channel: 'worklist' });
    });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('says the list has stopped updating the moment the socket drops', async () => {
    vi.useFakeTimers();
    try {
      const { view } = setup(vi.fn());
      act(() => FakeSocket.instances[0]!.open());
      act(() => FakeSocket.instances[0]!.drop());
      // Not "reconnecting" quietly behind a list that looks current.
      expect(view.result.current.status).toBe('reconnecting');
    } finally {
      vi.useRealTimers();
    }
  });

  it('refetches on reconnect rather than replaying the gap', async () => {
    vi.useFakeTimers();
    try {
      const onChange = vi.fn();
      const { view } = setup(onChange);
      act(() => FakeSocket.instances[0]!.open());
      // The first connection is not a reconnect: the initial fetch already
      // happened, and refetching here would double every page load.
      expect(onChange).not.toHaveBeenCalled();

      act(() => FakeSocket.instances[0]!.drop());
      act(() => {
        vi.advanceTimersByTime(1_000);
      });
      expect(FakeSocket.instances).toHaveLength(2);

      act(() => FakeSocket.instances[1]!.open());
      // Whatever happened during the gap is not recoverable from the stream,
      // so the list comes from the API instead.
      expect(onChange).toHaveBeenCalledTimes(1);
      expect(view.result.current.status).toBe('live');
    } finally {
      vi.useRealTimers();
    }
  });

  it('backs off rather than reconnecting in a tight loop', async () => {
    vi.useFakeTimers();
    try {
      setup(vi.fn());
      act(() => FakeSocket.instances[0]!.open());
      act(() => FakeSocket.instances[0]!.drop());
      act(() => {
        vi.advanceTimersByTime(1_000);
      });
      act(() => FakeSocket.instances[1]!.drop());
      // The second retry waits longer than the first. A hospital LAN drops for
      // seconds, and a client that retries every 50ms is a small DoS.
      act(() => {
        vi.advanceTimersByTime(1_500);
      });
      expect(FakeSocket.instances).toHaveLength(2);
      act(() => {
        vi.advanceTimersByTime(1_000);
      });
      expect(FakeSocket.instances).toHaveLength(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it('drops a frame it cannot parse without acting on it', async () => {
    const onChange = vi.fn();
    setup(onChange);
    act(() => FakeSocket.instances[0]!.open());
    act(() => FakeSocket.instances[0]!.onmessage?.(
      new MessageEvent('message', { data: 'not json' }),
    ));
    expect(onChange).not.toHaveBeenCalled();
  });
});
