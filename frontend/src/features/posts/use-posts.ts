import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type QueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useMe } from "@/features/auth/use-auth";
import { apiFetch } from "@/lib/api";
import type { FeedEntry, FeedPage as Page, Post } from "./types";

const PAGE_SIZE = 20;
const LIST_KEYS = [["timeline"], ["user-posts"], ["bookmarks"]] as const;

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

export function useBookmarks() {
  return useInfiniteQuery(pagedQuery(["bookmarks"], "/api/v1/me/bookmarks"));
}

function mapCachedPages(
  client: QueryClient,
  update: (items: FeedEntry[]) => FeedEntry[],
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
    mutationFn: (input: { body: string; files: File[]; quoteOf?: string }) => {
      const body = new FormData();
      body.append("body", input.body);
      if (input.quoteOf) body.append("quote_of_id", input.quoteOf);
      for (const file of input.files) body.append("files", file);
      return apiFetch<Post>("/api/v1/posts", { method: "POST", body });
    },
    onSuccess: (_, input) => {
      void client.invalidateQueries({ queryKey: ["timeline"] });
      if (input.quoteOf) {
        void client.invalidateQueries({ queryKey: ["post", input.quoteOf] });
      }
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
        items.map((item) =>
          item.post.id === post.id ? { ...item, post } : item,
        ),
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
      const orphan = (post: Post): Post =>
        post.quote?.id === id
          ? { ...post, quote: null, quote_unavailable: true }
          : post;
      mapCachedPages(client, (items) =>
        items
          .filter((item) => item.post.id !== id)
          .map((item) => ({ ...item, post: orphan(item.post) })),
      );
      client.removeQueries({ queryKey: ["post", id] });
      client.setQueriesData<Post>({ queryKey: ["post"] }, (post) =>
        post ? orphan(post) : post,
      );
    },
  });
}

type Interaction = "like" | "repost" | "bookmark";

const STATE = {
  like: { flag: "liked", count: "like_count" },
  repost: { flag: "reposted", count: "repost_count" },
  bookmark: { flag: "bookmarked", count: null },
} as const;

function toggled(post: Post, kind: Interaction, on: boolean): Post {
  const { flag, count } = STATE[kind];
  if (post[flag] === on) return post;
  const next = { ...post, [flag]: on };
  if (count) next[count] = Math.max(0, post[count] + (on ? 1 : -1));
  return next;
}

function useInteraction(kind: Interaction, id: string) {
  const client = useQueryClient();
  const { t } = useTranslation();

  function replace(update: (post: Post) => Post) {
    mapCachedPages(client, (items) =>
      items.map((item) =>
        item.post.id === id ? { ...item, post: update(item.post) } : item,
      ),
    );
    client.setQueryData<Post>(["post", id], (post) =>
      post ? update(post) : post,
    );
  }

  return useMutation({
    mutationFn: (input: { on: boolean }) =>
      apiFetch<Post>(`/api/v1/posts/${encodeURIComponent(id)}/${kind}`, {
        method: input.on ? "PUT" : "DELETE",
      }),
    onMutate: async ({ on }) => {
      await Promise.all(
        [["post", id], ...LIST_KEYS].map((queryKey) =>
          client.cancelQueries({ queryKey }),
        ),
      );
      replace((post) => toggled(post, kind, on));
      if (kind === "bookmark" && !on) {
        client.setQueriesData<Pages>({ queryKey: ["bookmarks"] }, (data) =>
          data
            ? {
                ...data,
                pages: data.pages.map((page) => ({
                  ...page,
                  items: page.items.filter((item) => item.post.id !== id),
                })),
              }
            : data,
        );
      }
    },
    onError: (_, { on }) => {
      replace((post) => toggled(post, kind, !on));
      void client.invalidateQueries({ queryKey: ["post", id] });
      if (kind === "bookmark") {
        void client.invalidateQueries({ queryKey: ["bookmarks"] });
      }
      toast.error(t("posts.actionFailed"));
    },
    onSuccess: (post, { on }) => {
      replace(() => post);
      if (kind === "bookmark" && on) {
        void client.invalidateQueries({ queryKey: ["bookmarks"] });
      }
      if (kind === "repost") {
        void client.invalidateQueries({ queryKey: ["user-posts"] });
      }
    },
  });
}

export const useLike = (id: string) => useInteraction("like", id);
export const useRepost = (id: string) => useInteraction("repost", id);
export const useBookmark = (id: string) => useInteraction("bookmark", id);
