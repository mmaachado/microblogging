import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/features/auth/use-auth";
import { ApiError } from "@/lib/api";
import { PostCard } from "./post-card";
import { usePost } from "./use-posts";

export function PostPage() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const post = usePost(id);

  if (post.isPending) return <p className="p-4">{t("common.loading")}</p>;
  if (post.isError) {
    const notFound =
      post.error instanceof ApiError && post.error.status === 404;
    return (
      <div className="flex flex-col items-center gap-4 p-8">
        <p role={notFound ? undefined : "alert"} className="text-lg font-bold">
          {notFound ? t("posts.notFound") : errorMessage(t, post.error)}
        </p>
        {!notFound && (
          <Button onClick={() => void post.refetch()}>
            {t("common.retry")}
          </Button>
        )}
      </div>
    );
  }
  return <PostCard post={post.data} onDeleted={() => void navigate("/")} />;
}
