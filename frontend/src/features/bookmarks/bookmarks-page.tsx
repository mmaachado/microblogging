import { useTranslation } from "react-i18next";
import { PostList } from "@/features/posts/post-list";
import { useBookmarks } from "@/features/posts/use-posts";

export function BookmarksPage() {
  const { t } = useTranslation();
  const bookmarks = useBookmarks();
  return (
    <>
      <h2 className="border-b p-4 text-xl font-bold">
        {t("bookmarks.title")}
      </h2>
      <PostList query={bookmarks} emptyText={t("bookmarks.empty")} />
    </>
  );
}
