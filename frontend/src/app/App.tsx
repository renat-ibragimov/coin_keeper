import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
import { CatalogPage } from '@/features/catalog/CatalogPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { ThemeProvider } from '@/shared/theme/ThemeProvider';

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

export function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
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
                  <Route
                    path="/catalog/new"
                    element={<ComingSoon titleKey="catalog.createOwn" />}
                  />
                  <Route path="/catalog/:id" element={<CoinCardPage />} />
                  <Route path="/import" element={<ComingSoon titleKey="catalog.importUcoin" />} />
                  <Route path="/series" element={<ComingSoon titleKey="nav.series" />} />
                  <Route path="/collection" element={<ComingSoon titleKey="nav.collection" />} />
                  <Route
                    path="/collection/new"
                    element={<ComingSoon titleKey="card.addPurchase" />}
                  />
                  <Route path="/missing" element={<ComingSoon titleKey="nav.missing" />} />
                  <Route path="/settings" element={<ComingSoon titleKey="nav.settings" />} />
                </Route>
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
