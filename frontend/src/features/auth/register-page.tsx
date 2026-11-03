import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage, useRegister } from "./use-auth";

const MIN_PASSWORD = 12;

export function RegisterPage() {
  const { t } = useTranslation();
  const register = useRegister();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);

  const mismatch = confirm !== "" && confirm !== password;
  const canSubmit =
    email !== "" &&
    password.length >= MIN_PASSWORD &&
    password === confirm &&
    acknowledged &&
    !register.isPending;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    register.mutate({
      email,
      password,
      acknowledged_email_notice: true,
    });
  };

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t("register.title")}</CardTitle>
        </CardHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-6">
          <CardContent className="flex flex-col gap-4">
            {register.isError && (
              <Alert variant="destructive" role="alert">
                <AlertDescription>
                  {errorMessage(t, register.error)}
                </AlertDescription>
              </Alert>
            )}
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">{t("common.email")}</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">{t("common.password")}</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD}
                maxLength={128}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <p className="text-muted-foreground text-xs">
                {t("register.passwordHint")}
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="confirm">{t("register.confirmPassword")}</Label>
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                required
                aria-invalid={mismatch}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
              {mismatch && (
                <p className="text-destructive text-xs">
                  {t("register.passwordMismatch")}
                </p>
              )}
            </div>
            <Alert>
              <AlertTitle>{t("register.noticeTitle")}</AlertTitle>
              <AlertDescription>{t("register.notice")}</AlertDescription>
            </Alert>
            <div className="flex items-center gap-2">
              <Checkbox
                id="acknowledge"
                checked={acknowledged}
                onCheckedChange={(value) => setAcknowledged(value === true)}
              />
              <Label htmlFor="acknowledge">{t("register.acknowledge")}</Label>
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={!canSubmit}>
              {register.isPending
                ? t("register.submitting")
                : t("register.submit")}
            </Button>
            <p className="text-muted-foreground text-sm">
              {t("register.hasAccount")}{" "}
              <Link to="/login" className="text-foreground underline">
                {t("register.login")}
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </main>
  );
}
