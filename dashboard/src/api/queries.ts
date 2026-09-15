/**
 * Every call this dashboard makes, in one file — 3/3 §3.
 *
 * TanStack Query owns server state; there is no second copy of a report in a
 * store somewhere. That matters more here than in most apps: two copies of a
 * clinical record differ eventually, and the one on screen is the one a
 * physician acts on.
 *
 * **Nothing here derives clinical content** (§1 rule 1). These are transport
 * and cache-invalidation decisions only.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query';

import { api } from './client';
import type {
  AlertList,
  CorrectionRate,
  DocumentRef,
  EvidencePayload,
  Fact,
  FactValue,
  Intake,
  PhysicianAction,
  Report,
  Worklist,
  WorklistState,
} from './types';

/**
 * Cache keys, built in one place.
 *
 * A stale worklist is a scheduling annoyance; a stale report is a physician
 * reading yesterday's answers. Both invalidate from here, so a new write path
 * cannot forget one of them.
 */
export const keys = {
  worklist: (department: string | null, states: readonly WorklistState[]) =>
    ['worklist', department, [...states].sort().join(',')] as const,
  alerts: (acknowledged: boolean | null, department: string | null) =>
    ['alerts', acknowledged, department] as const,
  intake: (intakeId: string) => ['intake', intakeId] as const,
  report: (intakeId: string, language: string | null) =>
    ['report', intakeId, language] as const,
  documents: (intakeId: string) => ['documents', intakeId] as const,
  evidence: (intakeId: string, factId: string) =>
    ['evidence', intakeId, factId] as const,
  correctionRate: () => ['metrics', 'correction-rate'] as const,
};

function query(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') {
      search.append(key, String(value));
    }
  }
  const rendered = search.toString();
  return rendered ? `?${rendered}` : '';
}

export function useWorklist(
  department: string | null,
  states: readonly WorklistState[],
  options?: Partial<UseQueryOptions<Worklist>>,
) {
  return useQuery<Worklist>({
    queryKey: keys.worklist(department, states),
    queryFn: () => {
      const search = new URLSearchParams();
      if (department) search.append('department', department);
      for (const state of states) search.append('state', state);
      const rendered = search.toString();
      return api.get<Worklist>(`/worklist${rendered ? `?${rendered}` : ''}`);
    },
    ...options,
  });
}

export function useAlerts(
  acknowledged: boolean | null,
  department: string | null,
) {
  return useQuery<AlertList>({
    queryKey: keys.alerts(acknowledged, department),
    queryFn: () =>
      api.get<AlertList>(`/alerts${query({ acknowledged, department })}`),
  });
}

export function useIntake(intakeId: string) {
  return useQuery<Intake>({
    queryKey: keys.intake(intakeId),
    queryFn: () => api.get<Intake>(`/intakes/${intakeId}`),
  });
}

export function useReport(intakeId: string, language: string | null = null) {
  return useQuery<Report>({
    queryKey: keys.report(intakeId, language),
    queryFn: () => {
      const params = language && language !== 'en' ? { language } : {};
      return api.get<Report>(`/intakes/${intakeId}/report${query(params)}`);
    },
  });
}

export function useDocuments(intakeId: string) {
  return useQuery<DocumentRef[]>({
    queryKey: keys.documents(intakeId),
    queryFn: () => api.get<DocumentRef[]>(`/intakes/${intakeId}/documents`),
  });
}

/**
 * One fact's evidence. Only fetched once a line has been clicked.
 *
 * Prefetching every line would put the whole record's transcript in the browser
 * before anyone asked to see it, which is more clinical text in memory than the
 * screen needs and more requests than the backend deserves.
 */
export function useEvidence(intakeId: string, factId: string | null) {
  return useQuery<EvidencePayload>({
    queryKey: keys.evidence(intakeId, factId ?? ''),
    queryFn: () =>
      api.get<EvidencePayload>(
        `/intakes/${intakeId}/facts/${factId}/evidence`,
      ),
    enabled: factId !== null,
  });
}

export function useCorrectionRate() {
  return useQuery<CorrectionRate>({
    queryKey: keys.correctionRate(),
    queryFn: () => api.get<CorrectionRate>('/metrics/correction-rate'),
  });
}

export interface FactAction {
  factId: string;
  action: PhysicianAction;
  value?: FactValue;
  reason?: string;
}

/**
 * Accept, amend or reject one fact — §6.
 *
 * On success the report and the record are **refetched, not patched**. The
 * backend writes a revision and rebuilds the report; a client that spliced the
 * returned fact into its cached copy would be re-deriving what the report says,
 * which is the thing §1 rule 1 forbids — and would quietly diverge the moment a
 * correction changed a conflict or a coverage count.
 */
export function useVerifyFact(intakeId: string) {
  const client = useQueryClient();
  return useMutation<Fact, Error, FactAction>({
    mutationFn: ({ factId, action, value, reason }) =>
      api.post<Fact>(`/intakes/${intakeId}/facts/${factId}/verify`, {
        action,
        ...(value === undefined ? {} : { value }),
        ...(reason === undefined ? {} : { reason }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.intake(intakeId) });
      void client.invalidateQueries({ queryKey: ['report', intakeId] });
      void client.invalidateQueries({ queryKey: ['worklist'] });
      void client.invalidateQueries({ queryKey: keys.correctionRate() });
    },
  });
}

/** Sign off everything settled on the record — §6's accept-all, at record scope. */
export function useVerifyRecord(intakeId: string) {
  const client = useQueryClient();
  return useMutation<Report, Error, { fieldIds?: readonly string[] }>({
    mutationFn: ({ fieldIds }) =>
      api.post<Report>(`/intakes/${intakeId}/verify`, {
        ...(fieldIds ? { field_ids: [...fieldIds] } : {}),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.intake(intakeId) });
      void client.invalidateQueries({ queryKey: ['report', intakeId] });
      void client.invalidateQueries({ queryKey: ['worklist'] });
      void client.invalidateQueries({ queryKey: keys.correctionRate() });
    },
  });
}

/**
 * Record that a person has seen an alert — §4.3.
 *
 * **This is not escalation.** It notifies nobody, reorders nothing, and there
 * is deliberately no `escalate` option on this mutation: the second action is a
 * second control, wired separately, so the two cannot collapse into one by
 * somebody adding a parameter here.
 */
export function useAcknowledgeAlert() {
  const client = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { intakeId: string; ruleId: string; note?: string }
  >({
    mutationFn: ({ intakeId, ruleId, note }) =>
      api.post(`/alerts/${intakeId}/acknowledge`, {
        rule_id: ruleId,
        ...(note ? { note } : {}),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['alerts'] });
      void client.invalidateQueries({ queryKey: ['worklist'] });
    },
  });
}
