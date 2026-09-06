/**
 * A dashboard left open on a shared OPD terminal — 3/3 §8.
 *
 * Not a theoretical exposure. The terminal is in a corridor, the physician is
 * called away, and the next person to sit down has a patient's history on
 * screen. So the session clears itself: a warning first, because clearing
 * without one loses an amendment somebody was halfway through typing, and then
 * a hard clear whether or not anybody saw the warning.
 *
 * Activity is anything a person does — pointer, key, scroll. Not a timer that
 * resets on background network traffic, which would keep a session alive on an
 * empty desk for as long as the worklist kept polling.
 */
import { useEffect, useRef, useState } from 'react';
import { IDLE_LIMIT_MS, IDLE_WARNING_MS, useSession } from './session';

const ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart'] as const;

export interface IdleState {
  /** True once the warning window has been entered. */
  warning: boolean;
  /** Seconds left before the session clears, or `null` outside the window. */
  secondsLeft: number | null;
  /** Dismiss the warning by declaring activity. */
  staySignedIn: () => void;
}

export function useIdleTimeout(enabled: boolean): IdleState {
  const signOut = useSession((state) => state.signOut);
  const [warning, setWarning] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const lastActivity = useRef(Date.now());

  useEffect(() => {
    if (!enabled) {
      setWarning(false);
      setSecondsLeft(null);
      return;
    }

    const touch = () => {
      lastActivity.current = Date.now();
    };
    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, touch, { passive: true });
    }

    // One second is fine granularity for a fifteen-minute window and costs
    // nothing; a `setTimeout` rescheduled on every keystroke does not survive a
    // physician typing an amendment.
    const tick = setInterval(() => {
      const idle = Date.now() - lastActivity.current;
      const remaining = IDLE_LIMIT_MS - idle;
      if (remaining <= 0) {
        signOut('idle');
        return;
      }
      if (remaining <= IDLE_WARNING_MS) {
        setWarning(true);
        setSecondsLeft(Math.ceil(remaining / 1000));
      } else if (remaining > IDLE_WARNING_MS) {
        setWarning(false);
        setSecondsLeft(null);
      }
    }, 1000);

    return () => {
      clearInterval(tick);
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, touch);
      }
    };
  }, [enabled, signOut]);

  return {
    warning,
    secondsLeft,
    staySignedIn: () => {
      lastActivity.current = Date.now();
      setWarning(false);
      setSecondsLeft(null);
    },
  };
}
