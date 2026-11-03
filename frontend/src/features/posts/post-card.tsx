import { MoreHorizontal } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage, useMe } from "@/features/auth/use-auth";
import { ProfileAvatar } from "@/features/profile/profile-avatar";
import { cn } from "@/lib/utils";
import { MAX_BODY, bodyLength } from "./body";
import { BodyCounter } from "./body-counter";
import type { Post, PostMedia } from "./types";
import { useDeletePost, useEditPost } from "./use-posts";

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31536000],
  ["month", 2592000],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

function relativeTime(iso: string, language: string): string {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
  const format = new Intl.RelativeTimeFormat(language, { numeric: "auto" });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) {
      return format.format(Math.trunc(seconds / size), unit);
    }
  }
  return format.format(seconds, "second");
}

function MediaGrid({ media }: { media: PostMedia[] }) {
  const { t } = useTranslation();
  if (media.length === 0) return null;
  const video = media[0].kind === "video";
  return (
    <div
      className={cn(
        "grid gap-1 overflow-hidden rounded-lg",
        media.length > 1 && "grid-cols-2",
      )}
    >
      {media.map((item, index) =>
        video ? (
          <video
            key={item.url}
            src={item.url}
            controls
            aria-label={t("posts.mediaVideo")}
            preload="metadata"
            playsInline
            className="max-h-96 w-full"
          />
        ) : (
          <img
            key={item.url}
            src={item.url}
            alt={t("posts.mediaAlt", { n: index + 1 })}
            loading="lazy"
            className={cn(
              "w-full object-cover",
              media.length === 1 ? "max-h-96" : "aspect-square",
            )}
          />
        ),
      )}
    </div>
  );
}

function EditForm({ post, onDone }: { post: Post; onDone: () => void }) {
  const { t } = useTranslation();
  const edit = useEditPost();
  const [body, setBody] = useState(post.body);
  const over = bodyLength(body) > MAX_BODY;
  const empty = body.trim() === "" && post.media.length === 0;
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        edit.mutate({ id: post.id, body }, { onSuccess: onDone });
      }}
    >
      <Textarea
        value={body}
        onChange={(event) => setBody(event.target.value)}
        aria-label={t("posts.edit")}
        aria-invalid={over}
      />
      {edit.isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(t, edit.error)}</AlertDescription>
        </Alert>
      )}
      <div className="flex items-center justify-between">
        <BodyCounter value={body} />
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onDone}>
            {t("posts.cancel")}
          </Button>
          <Button type="submit" disabled={edit.isPending || over || empty}>
            {t(edit.isPending ? "posts.saving" : "posts.save")}
          </Button>
        </div>
      </div>
    </form>
  );
}

function DeleteDialog({
  post,
  open,
  onOpenChange,
  onDeleted,
}: {
  post: Post;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: () => void;
}) {
  const { t } = useTranslation();
  const remove = useDeletePost();
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("posts.deleteTitle")}</AlertDialogTitle>
          <AlertDialogDescription>
            {t("posts.deleteDescription")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {remove.isError && (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage(t, remove.error)}</AlertDescription>
          </Alert>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel>{t("posts.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            disabled={remove.isPending}
            onClick={(event) => {
              event.preventDefault();
              remove.mutate(post.id, { onSuccess: onDeleted });
            }}
          >
            {t(remove.isPending ? "posts.deleting" : "posts.delete")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export function PostCard({
  post,
  onDeleted,
}: {
  post: Post;
  onDeleted?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const { data: me } = useMe();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const { author } = post;
  const profile = `/${author.username}`;
  const isAuthor = me?.username === author.username;

  return (
    <article className="flex gap-3 border-b p-4">
      <Link to={profile} className="shrink-0">
        <ProfileAvatar
          avatarUrl={author.avatar_url}
          name={author.display_name || author.username}
          className="size-10"
        />
      </Link>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
            {author.display_name && (
              <Link to={profile} className="font-bold hover:underline">
                {author.display_name}
              </Link>
            )}
            <Link to={profile} className="text-muted-foreground">
              @{author.username}
            </Link>
            <Link
              to={`/post/${post.id}`}
              title={new Date(post.created_at).toLocaleString(i18n.language)}
              className="text-muted-foreground text-sm hover:underline"
            >
              {relativeTime(post.created_at, i18n.language)}
            </Link>
            {post.edited_at && (
              <span className="text-muted-foreground text-sm">
                {t("posts.edited")}
              </span>
            )}
          </div>
          {isAuthor && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("posts.options")}
                >
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setEditing(true)}>
                  {t("posts.edit")}
                </DropdownMenuItem>
                <DropdownMenuItem
                  variant="destructive"
                  onSelect={() => setConfirming(true)}
                >
                  {t("posts.delete")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
        {editing ? (
          <EditForm post={post} onDone={() => setEditing(false)} />
        ) : (
          post.body && (
            <p className="break-words whitespace-pre-wrap">{post.body}</p>
          )
        )}
        <MediaGrid media={post.media} />
      </div>
      {isAuthor && (
        <DeleteDialog
          post={post}
          open={confirming}
          onOpenChange={setConfirming}
          onDeleted={onDeleted}
        />
      )}
    </article>
  );
}
