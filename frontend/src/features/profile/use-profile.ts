import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ME_KEY, type Me } from "@/features/auth/use-auth";
import { apiFetch } from "@/lib/api";

export interface PublicProfile {
  username: string;
  display_name: string;
  bio: string;
  avatar_url: string | null;
}

export interface ProfileUpdate {
  username?: string;
  display_name?: string;
  bio?: string;
  birthday?: string | null;
  phone?: string | null;
}

export function useProfile(username: string) {
  return useQuery({
    queryKey: ["profile", username],
    queryFn: () =>
      apiFetch<PublicProfile>(
        `/api/v1/users/${encodeURIComponent(username)}`,
      ),
    retry: false,
  });
}

function useMeMutation<V = void>(
  request: (input: V) => Promise<Me>,
  onRenamed?: (username: string) => void,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (me) => {
      const previous = client.getQueryData<Me | null>(ME_KEY);
      client.setQueryData(ME_KEY, me);
      client.setQueryData<PublicProfile>(["profile", me.username], {
        username: me.username,
        display_name: me.display_name,
        bio: me.bio,
        avatar_url: me.avatar_url,
      });
      if (previous && previous.username !== me.username) {
        onRenamed?.(me.username);
        void client.invalidateQueries({
          queryKey: ["profile", previous.username],
          exact: true,
          refetchType: "none",
        });
      }
    },
  });
}

export function useUpdateProfile(onRenamed?: (username: string) => void) {
  return useMeMutation(
    (input: ProfileUpdate) =>
      apiFetch<Me>("/api/v1/me", { method: "PATCH", body: input }),
    onRenamed,
  );
}

export function useUploadAvatar() {
  return useMeMutation((file: File) => {
    const body = new FormData();
    body.append("file", file);
    return apiFetch<Me>("/api/v1/me/avatar", { method: "PUT", body });
  });
}

export function useRemoveAvatar() {
  return useMeMutation(() =>
    apiFetch<Me>("/api/v1/me/avatar", { method: "DELETE" }),
  );
}
