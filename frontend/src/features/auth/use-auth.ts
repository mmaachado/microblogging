import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { TFunction } from "i18next";
import { ApiError, apiFetch } from "@/lib/api";

export interface Me {
  id: string;
  email: string;
  username: string;
  display_name: string;
  bio: string;
  avatar_url: string | null;
  birthday: string | null;
  phone: string | null;
  created_at: string;
}

interface Credentials {
  email: string;
  password: string;
}

interface RegisterInput extends Credentials {
  acknowledged_email_notice: boolean;
}

export const ME_KEY = ["me"] as const;

export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await apiFetch<Me>("/api/v1/auth/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: Infinity,
  });
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: Credentials) =>
      apiFetch<Me>("/api/v1/auth/login", { method: "POST", body: input }),
    onSuccess: (me) => client.setQueryData(ME_KEY, me),
  });
}

export function useRegister() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: RegisterInput) =>
      apiFetch<Me>("/api/v1/auth/register", { method: "POST", body: input }),
    onSuccess: (me) => client.setQueryData(ME_KEY, me),
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>("/api/v1/auth/logout", { method: "POST" }),
    onSettled: () => {
      client.clear();
      client.setQueryData(ME_KEY, null);
    },
  });
}

export function errorMessage(t: TFunction, error: unknown): string {
  const code = error instanceof ApiError ? error.detail : "unknown_error";
  return t(`errors.${code}`, { defaultValue: t("errors.unknown_error") });
}
