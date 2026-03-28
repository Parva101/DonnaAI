import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router";

/**
 * Handles the redirect after Google OAuth callback.
 *
 * The backend redirects here after processing the OAuth exchange:
 *   - /settings?connected=google  → connection success
 *   - /settings?error=oauth_failed → something went wrong
 *
 * The /dashboard redirect after login is handled directly by the backend
 * (it sets the session cookie and redirects), so the AppShell will pick
 * up the user automatically on next render.
 *
 * This page handles the "connect" callback specifically.
 */
export function OAuthCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const connected = params.get("connected");
    const error = params.get("error");

    if (connected) {
      // Redirect to settings with a success toast-like param
      navigate(`/settings?connected=${connected}`, { replace: true });
    } else if (error) {
      navigate(`/settings?error=${error}`, { replace: true });
    } else {
      navigate("/", { replace: true });
    }
  }, [params, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground text-sm">Completing sign-in…</p>
    </div>
  );
}
