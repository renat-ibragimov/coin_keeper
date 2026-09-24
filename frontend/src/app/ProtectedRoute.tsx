import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { guestDestination } from '@/features/auth/authReturn';
import { useAuth } from '@/features/auth/useAuth';
import { Spinner } from '@/shared/ui';

export function ProtectedRoute() {
  const { user, ready, sessionEnd } = useAuth();
  const location = useLocation();

  if (!ready) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: '60vh' }}>
        <Spinner size={32} />
      </div>
    );
  }
  if (!user) {
    // The global auth dialog handles explicit exits and expired sessions once.
    if (sessionEnd) return null;
    const from = location.pathname + location.search + location.hash;
    return (
      <Navigate
        to={guestDestination(from)}
        replace
        state={{
          authRequest: { mode: 'login', from, returnState: location.state },
        }}
      />
    );
  }
  return <Outlet />;
}
