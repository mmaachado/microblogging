import type {
  InfiniteData,
  UseInfiniteQueryResult,
} from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/features/auth/use-auth";
import { PostCard } from "./post-card";
import type { PostPage } from "./types";

export function PostList({
  query,
}: {
  query: UseInfiniteQueryResult<InfiniteData<PostPage>>;
}) {
  const { t } = useTranslation();
  if (query.isPending) return <p className="p-4">{t("posts.loading")}</p>;
  if (query.isError) {
    return (
      <div className="flex flex-col items-center gap-4 p-8">
        <p role="alert">{errorMessage(t, query.error)}</p>
        <Button onClick={() => void query.refetch()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }
  const posts = query.data.pages.flatMap((page) => page.items);
  if (posts.length === 0) {
    return (
      <p className="text-muted-foreground p-8 text-center">
        {t("posts.empty")}
      </p>
    );
  }
  return (
    <div>
      {posts.map((post) => (
        <PostCard key={post.id} post={post} />
      ))}
      {query.hasNextPage && (
        <div className="flex justify-center p-4">
          <Button
            variant="outline"
            disabled={query.isFetchingNextPage}
            onClick={() => void query.fetchNextPage()}
          >
            {t(
              query.isFetchingNextPage ? "posts.loadingMore" : "posts.loadMore",
            )}
          </Button>
        </div>
      )}
    </div>
  );
}
