import type { PublicProfile } from "@/features/profile/use-profile";

export interface PostMedia {
  kind: "image" | "video";
  url: string;
  mime: string;
}

export interface QuotedPost {
  id: string;
  author: PublicProfile;
  body: string;
  media: PostMedia[];
  created_at: string;
  edited_at: string | null;
  is_quote: boolean;
}

export interface Post {
  id: string;
  author: PublicProfile;
  body: string;
  media: PostMedia[];
  created_at: string;
  edited_at: string | null;
  like_count: number;
  repost_count: number;
  quote_count: number;
  liked: boolean;
  reposted: boolean;
  bookmarked: boolean;
  quote: QuotedPost | null;
  quote_unavailable: boolean;
}

export interface FeedEntry {
  post: Post;
  reposted_by: PublicProfile | null;
}

export interface FeedPage {
  items: FeedEntry[];
  next_cursor: string | null;
}
