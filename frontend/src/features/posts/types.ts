import type { PublicProfile } from "@/features/profile/use-profile";

export interface PostMedia {
  kind: "image" | "video";
  url: string;
  mime: string;
}

export interface Post {
  id: string;
  author: PublicProfile;
  body: string;
  media: PostMedia[];
  created_at: string;
  edited_at: string | null;
}

export interface PostPage {
  items: Post[];
  next_cursor: string | null;
}
