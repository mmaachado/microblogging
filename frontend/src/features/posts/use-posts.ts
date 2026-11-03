import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
} from "@tanstack/react-query";
import { useMe } from "@/features/auth/use-auth";
import { apiFetch } from "@/lib/api";
import type { Post, PostPage as Page } from "./types";

const PAGE_SIZE = 20;
const LIST_KEYS = [["timeline"], ["user-posts"]] as const;

type Pages = InfiniteData<Page, string | null>;

function listPath(base: string, cursor: string | null) {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (cursor) params.set("cursor", cursor);
  return `${base}?${params}`;
}

function pagedQuery(key: readonly unknown[], base: string) {
  return {
    queryKey: key,
    queryFn: ({ pageParam }: { pageParam: string | null }) =>
      apiFetch<Page>(listPath(base, pageParam)),
    initialPageParam: null as string | null,
    getNextPageParam: (last: Page) => last.next_cursor,
    retry: false,
  };
}

export function useTimeline() {
  return useInfiniteQuery(pagedQuery(["timeline"], "/api/v1/timeline"));
}

export function useUserPosts(username: string) {
  return useInfiniteQuery(
    pagedQuery(
      ["user-posts", username],
      `/api/v1/users/${encodeURIComponent(username)}/posts`,
    ),
  );
}

export function usePost(id: string) {
  return useQuery({
    queryKey: ["post", id],
    queryFn: () => apiFetch<Post>(`/api/v1/posts/${encodeURIComponent(id)}`),
    retry: false,
  });
}

function mapCachedPages(
  client: QueryClient,
  update: (items: Post[]) => Post[],
) {
  for (const queryKey of LIST_KEYS) {
    client.setQueriesData<Pages>({ queryKey }, (data) =>
      data
        ? {
            ...data,
            pages: data.pages.map((page) => ({
              ...page,
              items: update(page.items),
            })),
          }
        : data,
    );
  }
}

export function useCreatePost() {
  const client = useQueryClient();
  const { data: me } = useMe();
  return useMutation({
    mutationFn: (input: { body: string; files: File[] }) => {
      const body = new FormData();
      body.append("body", input.body);
      for (const file of input.files) body.append("files", file);
      return apiFetch<Post>("/api/v1/posts", { method: "POST", body });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["timeline"] });
      if (me) {
        void client.invalidateQueries({
          queryKey: ["user-posts", me.username],
        });
      }
    },
  });
}

export function useEditPost() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; body: string }) =>
      apiFetch<Post>(`/api/v1/posts/${encodeURIComponent(input.id)}`, {
        method: "PATCH",
        body: { body: input.body },
      }),
    onSuccess: (post) => {
      client.setQueryData(["post", post.id], post);
      mapCachedPages(client, (items) =>
        items.map((item) => (item.id === post.id ? post : item)),
      );
    },
  });
}

export function useDeletePost() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/v1/posts/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
    onSuccess: (_, id) => {
      mapCachedPages(client, (items) => items.filter((item) => item.id !== id));
      client.removeQueries({ queryKey: ["post", id] });
    },
  });
}
