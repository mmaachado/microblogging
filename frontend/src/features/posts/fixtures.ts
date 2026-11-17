import type { FeedEntry, Post } from "./types";

export const ME = {
  id: "1",
  email: "ana@example.com",
  username: "ana",
  display_name: "Ana",
  bio: "",
  avatar_url: null,
  birthday: null,
  phone: null,
  created_at: "2026-01-01T00:00:00Z",
};

export function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function makePost(overrides: Partial<Post> = {}): Post {
  return {
    id: "p1",
    author: {
      username: "ana",
      display_name: "Ana",
      bio: "",
      avatar_url: null,
    },
    body: "hello",
    media: [],
    created_at: new Date().toISOString(),
    edited_at: null,
    like_count: 0,
    repost_count: 0,
    quote_count: 0,
    liked: false,
    reposted: false,
    bookmarked: false,
    quote: null,
    quote_unavailable: false,
    ...overrides,
  };
}

export function makeEntry(
  post: Post,
  reposted_by: FeedEntry["reposted_by"] = null,
): FeedEntry {
  return { post, reposted_by };
}
