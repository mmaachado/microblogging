import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { useMe } from "@/features/auth/use-auth";
import { ApiError } from "@/lib/api";
import { EditProfileDialog } from "./edit-profile-dialog";
import { ProfileAvatar } from "./profile-avatar";
import { useProfile } from "./use-profile";

export function ProfilePage() {
  const { t } = useTranslation();
  const { username = "" } = useParams();
  const { data: me } = useMe();
  const profile = useProfile(username);
  const [editing, setEditing] = useState(false);

  if (profile.isPending) {
    return <p className="p-4">{t("common.loading")}</p>;
  }
  if (profile.isError) {
    const notFound =
      profile.error instanceof ApiError && profile.error.status === 404;
    return (
      <div className="flex flex-col items-center gap-4 p-8">
        <p role={notFound ? undefined : "alert"} className="text-lg font-bold">
          {t(notFound ? "profile.notFound" : "errors.unknown_error")}
        </p>
        {!notFound && (
          <Button onClick={() => void profile.refetch()}>
            {t("common.retry")}
          </Button>
        )}
      </div>
    );
  }

  const { data } = profile;
  const isOwn = me?.username === data.username;
  const shownName = data.display_name || `@${data.username}`;

  return (
    <section className="flex flex-col gap-4 p-4">
      <div className="flex items-start justify-between">
        <ProfileAvatar
          avatarUrl={data.avatar_url}
          name={data.display_name || data.username}
        />
        {isOwn && me && (
          <>
            <Button variant="outline" onClick={() => setEditing(true)}>
              {t("profile.edit")}
            </Button>
            <EditProfileDialog
              me={me}
              open={editing}
              onOpenChange={setEditing}
            />
          </>
        )}
      </div>
      <div>
        <h2 className="text-xl font-bold">{shownName}</h2>
        {data.display_name && (
          <p className="text-muted-foreground">@{data.username}</p>
        )}
      </div>
      {data.bio && (
        <p className="break-words whitespace-pre-wrap">{data.bio}</p>
      )}
    </section>
  );
}
