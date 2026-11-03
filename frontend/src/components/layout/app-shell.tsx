import { Home, Languages, LogOut, Monitor, Moon, Settings, Sun, User } from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet } from "react-router";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLogout, type Me } from "@/features/auth/use-auth";
import { LANGUAGES, setLanguage } from "@/i18n";
import { cn } from "@/lib/utils";
import { useTheme, type Theme } from "@/providers/theme-provider";

const THEMES: { value: Theme; icon: typeof Sun }[] = [
  { value: "light", icon: Sun },
  { value: "dark", icon: Moon },
  { value: "system", icon: Monitor },
];

function ThemeToggle() {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  const Icon = theme === "dark" ? Moon : Sun;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("theme.label")}>
          <Icon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {THEMES.map(({ value, icon: ItemIcon }) => (
          <DropdownMenuItem key={value} onSelect={() => setTheme(value)}>
            <ItemIcon />
            {t(`theme.${value}`)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function LanguageToggle() {
  const { t } = useTranslation();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("language.label")}>
          <Languages />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {LANGUAGES.map((language) => (
          <DropdownMenuItem
            key={language}
            onSelect={() => setLanguage(language)}
          >
            {t(`language.${language}`)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "hover:bg-accent flex items-center gap-3 rounded-full px-4 py-2 text-lg",
    "max-md:flex-col max-md:gap-0 max-md:rounded-md max-md:px-3 max-md:py-1 max-md:text-xs",
    isActive && "font-bold",
  );

export function AppShell({ me }: { me: Me }) {
  const { t } = useTranslation();
  const logout = useLogout();

  return (
    <div className="mx-auto flex min-h-svh max-w-6xl">
      <header className="max-md:bg-background fixed inset-x-0 bottom-0 z-10 border-t md:sticky md:top-0 md:h-svh md:w-64 md:border-t-0 md:border-r md:p-4">
        <div className="flex h-full flex-col max-md:flex-row">
          <h1 className="mb-4 hidden px-4 text-xl font-bold md:block">
            {t("app.name")}
          </h1>
          <nav
            aria-label={t("nav.primary")}
            className="flex flex-1 justify-around md:flex-col md:justify-start md:gap-1"
          >
            <NavLink to="/" end className={linkClass}>
              <Home className="size-5" />
              {t("nav.home")}
            </NavLink>
            <NavLink to={`/${me.username}`} className={linkClass}>
              <User className="size-5" />
              {t("nav.profile")}
            </NavLink>
            <NavLink to="/settings" className={linkClass}>
              <Settings className="size-5" />
              {t("nav.settings")}
            </NavLink>
            <button
              type="button"
              className={linkClass({ isActive: false })}
              onClick={() => logout.mutate()}
            >
              <LogOut className="size-5" />
              {t("nav.logout")}
            </button>
          </nav>
          <div className="flex items-center gap-1 max-md:hidden">
            <ThemeToggle />
            <LanguageToggle />
          </div>
        </div>
      </header>
      <main className="min-w-0 flex-1 pb-20 md:border-r md:pb-0">
        <div className="flex justify-end gap-1 p-2 md:hidden">
          <ThemeToggle />
          <LanguageToggle />
        </div>
        <Outlet />
      </main>
      <aside className="hidden w-72 p-4 lg:block">
        <div className="sticky top-4 flex flex-col gap-2 rounded-xl border p-4">
          <p className="font-bold">{t("app.name")}</p>
        </div>
      </aside>
    </div>
  );
}
