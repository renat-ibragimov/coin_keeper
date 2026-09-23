import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { BrowserRouter, Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom';

import { AdminPage } from '@/features/admin/AdminPage';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { AuthDialogProvider } from '@/features/auth/AuthDialog';
import { AuthLayout } from '@/features/auth/AuthLayout';
import { useAuth } from '@/features/auth/useAuth';
import { CheckEmailPage } from '@/features/auth/pages/CheckEmailPage';
import { ForgotPasswordPage } from '@/features/auth/pages/ForgotPasswordPage';
import { GoogleCompletePage } from '@/features/auth/pages/GoogleCompletePage';
import { LoginPage } from '@/features/auth/pages/LoginPage';
import { RegisterPage } from '@/features/auth/pages/RegisterPage';
import { ResetPasswordPage } from '@/features/auth/pages/ResetPasswordPage';
import { VerifyEmailPage } from '@/features/auth/pages/VerifyEmailPage';
import { CoinCardPage } from '@/features/catalog/card/CoinCardPage';
import { CatalogPage } from '@/features/catalog/CatalogPage';
import { parseFilters, serializeFilters } from '@/features/catalog/useCatalogFilters';
import { AddPage } from '@/features/collection/add/AddPage';
import { GuestCollectionPage } from '@/features/collection/guest/GuestCollectionPage';
import { CollectionPage } from '@/features/collection/CollectionPage';
import { PurchaseFormPage } from '@/features/collection/PurchaseFormPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { CompletenessDetailPage } from '@/features/completeness/CompletenessDetailPage';
import { CompletenessListPage } from '@/features/completeness/CompletenessListPage';
import { ExpensesPage } from '@/features/expenses/ExpensesPage';
import { SettingsPage } from '@/features/settings/SettingsPage';
import { scrollPageToTop } from '@/shared/lib/pageScroll';
import { ThemeProvider } from '@/shared/theme/ThemeProvider';
import { Spinner, ToastProvider } from '@/shared/ui';

import { AppLayout } from './layout/AppLayout';
import { DonationDialogProvider } from './layout/DonationDialog';
import { ProtectedRoute } from './ProtectedRoute';
import { ThemeSettingsSync } from './ThemeSettingsSync';
import { LegalPage } from './legal/LegalPage';

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
 * The app never restores scroll position across navigations — a new route
 * should land at the top, not wherever the previous page was scrolled to
 * (docs/08-ui-map.md).
 *
 * Keyed on pathname alone, not the query string: a search-string change on
 * the SAME path covers both "a new page of results" (pagination) and "the
 * same rows, just re-sorted" (a sortable column header) — and only the
 * first of those should jump the reader to the top. Pagination already
 * gets its own explicit scrollPageToTop() (shared/ui/Pagination.tsx); a
 * sort click clearing scroll position out from under someone reading the
 * table was the actual bug (owner-reported, 2026-09-13).
 */
function AuthCacheReset() {
  const { user } = useAuth();
  const client = useQueryClient();
  useEffect(() => {
    client.clear();
  }, [user?.id, client]);
  return null;
}

function ReadyRoute() {
  const { ready } = useAuth();
  return ready ? (
    <AuthDialogProvider>
      <AppLayout />
    </AuthDialogProvider>
  ) : (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: '60vh' }}>
      <Spinner size={32} />
    </div>
  );
}

export function RootRoute() {
  const { user } = useAuth();
  return <Navigate to={user ? '/collection' : '/catalog'} replace />;
}

export function CollectionRoot() {
  const { user } = useAuth();
  return user ? <DashboardPage /> : <GuestCollectionPage />;
}

function CollectionSectionRoute({ section }: { section: 'coins' | 'completeness' | 'money' }) {
  const { user } = useAuth();
  if (!user) return <GuestCollectionPage section={section} />;
  if (section === 'coins') return <CollectionPage />;
  if (section === 'completeness') return <CompletenessListPage />;
  return <ExpensesPage />;
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    scrollPageToTop();
  }, [pathname]);
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

/** `/series/:id` and the retired `/collection/series/:id` both land on the
 *  "Комплектність" detail screen, grouped by series. */
function RedirectSeriesDetail() {
  const { id } = useParams();
  const location = useLocation();
  return (
    <Navigate
      to={{
        pathname: `/collection/completeness/series/${id}`,
        search: location.search,
        hash: location.hash,
      }}
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
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <LocaleCacheReset />
        <ToastProvider>
          <AuthProvider>
            <ThemeSettingsSync />
            <AuthCacheReset />
            <BrowserRouter>
              <ScrollToTop />
              <DonationDialogProvider>
                <Routes>
                  <Route path="/privacy" element={<LegalPage kind="privacy" />} />
                  <Route path="/terms" element={<LegalPage kind="terms" />} />
                  <Route element={<AuthLayout />}>
                    <Route path="/login" element={<LoginPage />} />
                    <Route path="/register" element={<RegisterPage />} />
                    <Route path="/check-email" element={<CheckEmailPage />} />
                    <Route path="/verify-email" element={<VerifyEmailPage />} />
                    <Route path="/forgot-password" element={<ForgotPasswordPage />} />
                    <Route path="/google-complete" element={<GoogleCompletePage />} />
                    <Route path="/reset-password" element={<ResetPasswordPage />} />
                  </Route>
                  <Route element={<ReadyRoute />}>
                    <Route path="/collection" element={<CollectionRoot />} />
                    <Route
                      path="/collection/coins"
                      element={<CollectionSectionRoute section="coins" />}
                    />
                    <Route
                      path="/collection/completeness"
                      element={<CollectionSectionRoute section="completeness" />}
                    />
                    <Route
                      path="/collection/money"
                      element={<CollectionSectionRoute section="money" />}
                    />
                    <Route path="/catalog" element={<CatalogPage />} />
                    <Route path="/catalog/:id" element={<CoinCardPage />} />
                    <Route path="/" element={<RootRoute />} />
                    <Route element={<ProtectedRoute />}>
                      <Route path="/collection/add" element={<AddPage />} />
                      <Route path="/collection/coins/:id/edit" element={<PurchaseFormPage />} />
                      <Route
                        path="/collection/completeness/:groupBy/:value"
                        element={<CompletenessDetailPage />}
                      />
                      <Route path="/settings" element={<SettingsPage />} />
                      <Route path="/admin" element={<AdminRoute />} />

                      {/* Retired paths, kept as redirects for old bookmarks and links. */}
                      <Route path="/dashboard" element={<Navigate to="/collection" replace />} />
                      <Route
                        path="/series"
                        element={<Navigate to="/collection/completeness" replace />}
                      />
                      <Route path="/series/:id" element={<RedirectSeriesDetail />} />
                      <Route
                        path="/collection/series"
                        element={<Navigate to="/collection/completeness" replace />}
                      />
                      <Route path="/collection/series/:id" element={<RedirectSeriesDetail />} />
                      <Route path="/missing" element={<RedirectMissingToCatalog />} />
                      <Route path="/collection/missing" element={<RedirectMissingToCatalog />} />
                      <Route
                        path="/expenses"
                        element={<Navigate to="/collection/money" replace />}
                      />
                      <Route path="/collection/:id/edit" element={<RedirectCollectionEdit />} />
                      <Route path="/collection/new" element={<RedirectTo to="/collection/add" />} />
                      <Route
                        path="/collection/coins/new"
                        element={<RedirectTo to="/collection/add" />}
                      />
                    </Route>
                  </Route>
                  <Route path="*" element={<Navigate to="/catalog" replace />} />
                </Routes>
              </DonationDialogProvider>
            </BrowserRouter>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
