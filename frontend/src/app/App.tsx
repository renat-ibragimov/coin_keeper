import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom';

import { AdminPage } from '@/features/admin/AdminPage';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { AuthLayout } from '@/features/auth/AuthLayout';
import { useAuth } from '@/features/auth/useAuth';
import { CheckEmailPage } from '@/features/auth/pages/CheckEmailPage';
import { ForgotPasswordPage } from '@/features/auth/pages/ForgotPasswordPage';
import { LoginPage } from '@/features/auth/pages/LoginPage';
import { RegisterPage } from '@/features/auth/pages/RegisterPage';
import { ResetPasswordPage } from '@/features/auth/pages/ResetPasswordPage';
import { VerifyEmailPage } from '@/features/auth/pages/VerifyEmailPage';
import { CoinCardPage } from '@/features/catalog/card/CoinCardPage';
import { CatalogPage } from '@/features/catalog/CatalogPage';
import { parseFilters, serializeFilters } from '@/features/catalog/useCatalogFilters';
import { CollectionPage } from '@/features/collection/CollectionPage';
import { PurchaseFormPage } from '@/features/collection/PurchaseFormPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { ExpensesPage } from '@/features/expenses/ExpensesPage';
import { SeriesDetailPage } from '@/features/series/SeriesDetailPage';
import { SeriesListPage } from '@/features/series/SeriesListPage';
import { SettingsPage } from '@/features/settings/SettingsPage';
import { scrollPageToTop } from '@/shared/lib/pageScroll';
import { ThemeProvider } from '@/shared/theme/ThemeProvider';
import { ToastProvider } from '@/shared/ui';

import { ComingSoon } from './ComingSoon';
import { AppLayout } from './layout/AppLayout';
import { ProtectedRoute } from './ProtectedRoute';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/**
 * Cached answers are in the language they were fetched in.
 *
 * The API renders every name — coin titles, countries, series, denominations —
 * for the locale of the request, so switching the language makes the whole
 * cache stale at once. Clearing it is the honest response; per-locale query
 * keys would spread the same fact across every feature.
 */
function LocaleCacheReset() {
  const queryClient = useQueryClient();
  const { i18n } = useTranslation();
  useEffect(() => {
    const reset = () => queryClient.clear();
    i18n.on('languageChanged', reset);
    return () => i18n.off('languageChanged', reset);
  }, [i18n, queryClient]);
  return null;
}

/**
 * The app never restores scroll position across navigations — every route
 * change (a new page, or a pagination query-string change on the same
 * path) should land at the top, not wherever the previous page was scrolled
 * to (docs/08-ui-map.md).
 */
function ScrollToTop() {
  const { pathname, search } = useLocation();
  useEffect(() => {
    scrollPageToTop();
  }, [pathname, search]);
  return null;
}

/** The admin section is the one place a signed-in user can be turned away:
 *  the role is checked here as well as on every endpoint behind it. */
function AdminRoute() {
  const { user } = useAuth();
  if (user?.role !== 'admin') return <Navigate to="/collection" replace />;
  return <AdminPage />;
}

/** Redirects a retired path to `to`, keeping the query string and hash. */
function RedirectTo({ to }: { to: string }) {
  const location = useLocation();
  return <Navigate to={{ pathname: to, search: location.search, hash: location.hash }} replace />;
}

/** `/series/:id` moved under the collection context. */
function RedirectSeriesDetail() {
  const { id } = useParams();
  const location = useLocation();
  return (
    <Navigate
      to={{ pathname: `/collection/series/${id}`, search: location.search, hash: location.hash }}
      replace
    />
  );
}

/** `/collection/:id/edit` moved under `/collection/coins`. */
function RedirectCollectionEdit() {
  const { id } = useParams();
  const location = useLocation();
  return (
    <Navigate
      to={{
        pathname: `/collection/coins/${id}/edit`,
        search: location.search,
        hash: location.hash,
      }}
      replace
    />
  );
}

/**
 * The "missing" page is retired: the catalog's own "немає в колекції"
 * filter takes its place (docs/08-ui-map.md). Any filters bookmarked on the
 * old page (country, series, years — the page used the catalog's own filter
 * hook) share the catalog's query param vocabulary, so they carry over as-is;
 * `owned` is forced through the catalog's own serializer rather than a
 * hardcoded string, so it can never drift from what the catalog itself writes.
 */
function RedirectMissingToCatalog() {
  const location = useLocation();
  const params = serializeFilters({
    ...parseFilters(new URLSearchParams(location.search)),
    owned: false,
  });
  return (
    <Navigate
      to={{ pathname: '/catalog', search: `?${params.toString()}`, hash: location.hash }}
      replace
    />
  );
}

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <LocaleCacheReset />
        <ToastProvider>
          <AuthProvider>
            <BrowserRouter>
              <ScrollToTop />
              <Routes>
                <Route element={<AuthLayout />}>
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/register" element={<RegisterPage />} />
                  <Route path="/check-email" element={<CheckEmailPage />} />
                  <Route path="/verify-email" element={<VerifyEmailPage />} />
                  <Route path="/forgot-password" element={<ForgotPasswordPage />} />
                  <Route path="/reset-password" element={<ResetPasswordPage />} />
                </Route>
                <Route element={<ProtectedRoute />}>
                  <Route element={<AppLayout />}>
                    <Route path="/collection" element={<DashboardPage />} />
                    <Route path="/collection/coins" element={<CollectionPage />} />
                    <Route path="/collection/coins/new" element={<PurchaseFormPage />} />
                    <Route path="/collection/coins/:id/edit" element={<PurchaseFormPage />} />
                    <Route path="/collection/series" element={<SeriesListPage />} />
                    <Route path="/collection/series/:id" element={<SeriesDetailPage />} />
                    <Route path="/collection/money" element={<ExpensesPage />} />
                    <Route path="/catalog" element={<CatalogPage />} />
                    <Route path="/catalog/:id" element={<CoinCardPage />} />
                    <Route path="/import" element={<ComingSoon titleKey="catalog.importUcoin" />} />
                    <Route path="/settings" element={<SettingsPage />} />
                    <Route path="/admin" element={<AdminRoute />} />

                    {/* Retired paths, kept as redirects for old bookmarks and links. */}
                    <Route path="/" element={<Navigate to="/collection" replace />} />
                    <Route path="/dashboard" element={<Navigate to="/collection" replace />} />
                    <Route path="/series" element={<Navigate to="/collection/series" replace />} />
                    <Route path="/series/:id" element={<RedirectSeriesDetail />} />
                    <Route path="/missing" element={<RedirectMissingToCatalog />} />
                    <Route path="/collection/missing" element={<RedirectMissingToCatalog />} />
                    <Route path="/expenses" element={<Navigate to="/collection/money" replace />} />
                    <Route
                      path="/collection/new"
                      element={<RedirectTo to="/collection/coins/new" />}
                    />
                    <Route path="/collection/:id/edit" element={<RedirectCollectionEdit />} />
                  </Route>
                </Route>
                <Route path="*" element={<Navigate to="/collection" replace />} />
              </Routes>
            </BrowserRouter>
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
