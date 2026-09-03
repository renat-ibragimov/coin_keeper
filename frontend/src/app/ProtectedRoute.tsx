import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import { Spinner } from '@/shared/ui';

export function ProtectedRoute() {
  const { user, ready } = useAuth();
  const location = useLocation();

  if (!ready) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: '60vh' }}>
        <Spinner size={32} />
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}
