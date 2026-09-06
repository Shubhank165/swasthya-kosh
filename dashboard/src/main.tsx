/**
 * Entry point.
 *
 * `setAuthFailureHandler` is wired here and only here: when the server refuses,
 * the session clears and the refusal screen replaces whatever was on screen.
 * Failing closed has to be the default behaviour of the transport, not
 * something each screen remembers to do (§1 rule 6).
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

import { App } from './App';
import { ApiError, setAuthFailureHandler } from './api/client';
import { useSession } from './auth/session';
import './index.css';

setAuthFailureHandler(() => {
  useSession.getState().signOut('refused');
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The worklist is pushed over the socket and the report is refetched
      // after every write, so polling on focus would mostly re-fetch what is
      // already correct. What it must not do is retry a 403 four times: the
      // answer will not change and each attempt is another refused clinical
      // read in the audit log.
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.isAuthFailure) && failureCount < 2,
      refetchOnWindowFocus: true,
      staleTime: 15_000,
    },
    mutations: { retry: false },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
