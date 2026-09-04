import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AuthProvider } from '@/features/auth/AuthProvider';
import { AuthLayout } from '@/features/auth/AuthLayout';
import { CheckEmailPage } from '@/features/auth/pages/CheckEmailPage';
import { ForgotPasswordPage } from '@/features/auth/pages/ForgotPasswordPage';
import { LoginPage } from '@/features/auth/pages/LoginPage';
import { RegisterPage } from '@/features/auth/pages/RegisterPage';
import { ResetPasswordPage } from '@/features/auth/pages/ResetPasswordPage';
import { VerifyEmailPage } from '@/features/auth/pages/VerifyEmailPage';
import { CoinCardPage } from '@/features/catalog/card/CoinCardPage';
import { CreateItemPage } from '@/features/catalog/create/CreateItemPage';
import { CatalogPage } from '@/features/catalog/CatalogPage';
import { CollectionPage } from '@/features/collection/CollectionPage';
import { PurchaseFormPage } from '@/features/collection/PurchaseFormPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { ExpensesPage } from '@/features/expenses/ExpensesPage';
import { MissingPage } from '@/features/missing/MissingPage';
import { SeriesDetailPage } from '@/features/series/SeriesDetailPage';
import { SeriesListPage } from '@/features/series/SeriesListPage';
import { SettingsPage } from '@/features/settings/SettingsPage';
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

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <LocaleCacheReset />
        <ToastProvider>
          <AuthProvider>
            <BrowserRouter>
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
                    <Route path="/" element={<DashboardPage />} />
                    <Route path="/dashboard" element={<Navigate to="/" replace />} />
                    <Route path="/catalog" element={<CatalogPage />} />
                    <Route path="/catalog/new" element={<CreateItemPage />} />
                    <Route path="/catalog/:id" element={<CoinCardPage />} />
                    <Route path="/import" element={<ComingSoon titleKey="catalog.importUcoin" />} />
                    <Route path="/series" element={<SeriesListPage />} />
                    <Route path="/series/:id" element={<SeriesDetailPage />} />
                    <Route path="/collection" element={<CollectionPage />} />
                    <Route path="/collection/new" element={<PurchaseFormPage />} />
                    <Route path="/collection/:id/edit" element={<PurchaseFormPage />} />
                    <Route path="/missing" element={<MissingPage />} />
                    <Route path="/expenses" element={<ExpensesPage />} />
                    <Route path="/settings" element={<SettingsPage />} />
                    <Route path="/admin" element={<ComingSoon titleKey="settings.adminTitle" />} />
                  </Route>
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </BrowserRouter>
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
