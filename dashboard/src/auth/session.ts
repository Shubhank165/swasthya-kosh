/**
 * Who is looking at this screen — 3/3 §8.
 *
 * Four roles reach the dashboard: `physician`, `staff`, `triage`, `admin`.
 * **`patient` and `kiosk` tokens are refused outright** — they are credentials
 * issued to a phone and to a device in a corridor, and neither should ever
 * render a worklist. That check lives here rather than in a route guard so
 * there is one place it can be got wrong.
 */

import { create } from 'zustand';
import { setAccessToken } from '../api/client';

export const DASHBOARD_ROLES = ['physician', 'staff', 'triage', 'admin'] as const;
export type DashboardRole = (typeof DASHBOARD_ROLES)[number];

export function isDashboardRole(role: string): role is DashboardRole {
  return (DASHBOARD_ROLES as readonly string[]).includes(role);
}

export interface Session {
  userId: string;
  role: DashboardRole;
  hospitalId: string;
  departmentCode?: string | null;
}

/** How long a dashboard may sit untouched before it clears itself (§8). */
export const IDLE_LIMIT_MS = 15 * 60 * 1000;
/** How long before that the user is warned. */
export const IDLE_WARNING_MS = 2 * 60 * 1000;

interface SessionState {
  session: Session | null;
  /** Set when a session ended by itself, so the login screen can say why. */
  endedBecause: 'idle' | 'refused' | null;
  signIn: (session: Session, token: string) => void;
  signOut: (reason?: 'idle' | 'refused') => void;
}

export const useSession = create<SessionState>((set) => ({
  session: null,
  endedBecause: null,
  signIn: (session, token) => {
    setAccessToken(token);
    set({ session, endedBecause: null });
  },
  signOut: (reason) => {
    setAccessToken(null);
    set({ session: null, endedBecause: reason ?? null });
  },
}));

/**
 * Whether a role may see clinical content at all.
 *
 * Distinct from "may perform this action": verification is physician-only, and
 * that is enforced per control. This is the coarse gate that decides whether a
 * screen renders or a refusal does.
 */
export function canSeeClinicalContent(session: Session | null): boolean {
  return session !== null && isDashboardRole(session.role);
}
