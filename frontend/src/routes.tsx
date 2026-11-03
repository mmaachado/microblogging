import { useTranslation } from "react-i18next";
import { Navigate, Outlet, createBrowserRouter } from "react-router";
import { Button } from "@/components/ui/button";
import { AppShell } from "@/components/layout/app-shell";
import { LoginPage } from "@/features/auth/login-page";
import { RegisterPage } from "@/features/auth/register-page";
import { useMe } from "@/features/auth/use-auth";

function Loading() {
  const { t } = useTranslation();
  return <p className="p-4">{t("common.loading")}</p>;
}

export function ProtectedRoute() {
  const { t } = useTranslation();
  const { data, isPending, isError, refetch } = useMe();
  if (isPending) return <Loading />;
  if (isError) {
    return (
      <div className="flex flex-col items-center gap-4 p-8">
        <p role="alert">{t("errors.loadFailed")}</p>
        <Button onClick={() => void refetch()}>{t("common.retry")}</Button>
      </div>
    );
  }
  if (!data) return <Navigate to="/login" replace />;
  return <AppShell />;
}

function PublicRoute() {
  const { data, isPending } = useMe();
  if (isPending) return <Loading />;
  if (data) return <Navigate to="/" replace />;
  return <Outlet />;
}

function HomePage() {
  const { t } = useTranslation();
  return <p className="text-muted-foreground p-8 text-center">{t("home.empty")}</p>;
}

function ComingSoon() {
  const { t } = useTranslation();
  return <p className="text-muted-foreground p-8 text-center">{t("placeholder.soon")}</p>;
}

export const router = createBrowserRouter([
  {
    element: <PublicRoute />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/register", element: <RegisterPage /> },
    ],
  },
  {
    element: <ProtectedRoute />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/profile", element: <ComingSoon /> },
      { path: "/settings", element: <ComingSoon /> },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
