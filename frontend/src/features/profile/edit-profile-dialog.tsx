import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage, type Me } from "@/features/auth/use-auth";
import { ApiError } from "@/lib/api";
import { ProfileAvatar } from "./profile-avatar";
import {
  useRemoveAvatar,
  useUpdateProfile,
  useUploadAvatar,
} from "./use-profile";

const MAX_NAME = 50;
const MAX_BIO = 160;
const MAX_AVATAR_BYTES = 5 * 1024 * 1024;
const AVATAR_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const USERNAME_ERRORS = [
  "username_taken",
  "username_invalid",
  "username_reserved",
];
const length = (value: string) => [...value].length;

interface Props {
  me: Me;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function Counter({ value, max }: { value: string; max: number }) {
  return (
    <span className="text-muted-foreground text-xs">
      {length(value)}/{max}
    </span>
  );
}

function EditProfileForm({ me, onOpenChange }: Omit<Props, "open">) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const update = useUpdateProfile((renamed) => {
    void navigate(`/${renamed}`);
  });
  const upload = useUploadAvatar();
  const remove = useRemoveAvatar();
  const fileInput = useRef<HTMLInputElement>(null);
  const [displayName, setDisplayName] = useState(me.display_name);
  const [username, setUsername] = useState(me.username);
  const [bio, setBio] = useState(me.bio);
  const [birthday, setBirthday] = useState(me.birthday ?? "");
  const [phone, setPhone] = useState(me.phone ?? "");
  const [avatarError, setAvatarError] = useState<string | null>(null);

  const usernameError =
    update.error instanceof ApiError &&
    USERNAME_ERRORS.includes(update.error.detail)
      ? update.error.detail
      : null;
  const formError = update.isError && !usernameError ? update.error : null;
  const busy = update.isPending || upload.isPending || remove.isPending;
  const canSave =
    !busy &&
    length(displayName) <= MAX_NAME &&
    length(bio) <= MAX_BIO &&
    username.trim() !== "";

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    update.mutate(
      {
        username,
        display_name: displayName,
        bio,
        birthday: birthday || null,
        phone: phone.trim() || null,
      },
      {
        onSuccess: () => onOpenChange(false),
      },
    );
  };

  const onFile = (file: File | undefined) => {
    if (!file) return;
    setAvatarError(null);
    if (!AVATAR_TYPES.includes(file.type)) {
      setAvatarError("invalid_image");
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setAvatarError("file_too_large");
      return;
    }
    upload.mutate(file, {
      onError: (error) =>
        setAvatarError(
          error instanceof ApiError ? error.detail : "unknown_error",
        ),
    });
  };

  const onRemove = () => {
    setAvatarError(null);
    remove.mutate(undefined, {
      onError: (error) =>
        setAvatarError(
          error instanceof ApiError ? error.detail : "unknown_error",
        ),
    });
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {formError && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{errorMessage(t, formError)}</AlertDescription>
        </Alert>
      )}
      <div className="flex items-center gap-4">
        <ProfileAvatar
          avatarUrl={me.avatar_url}
          name={me.display_name || me.username}
          className="size-16"
        />
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            <input
              ref={fileInput}
              type="file"
              accept={AVATAR_TYPES.join(",")}
              className="hidden"
              data-testid="avatar-input"
              onChange={(e) => {
                onFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              {t("profile.changePhoto")}
            </Button>
            {me.avatar_url && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={onRemove}
              >
                {t("profile.removePhoto")}
              </Button>
            )}
          </div>
          {avatarError && (
            <p role="alert" className="text-destructive text-sm">
              {t(`errors.${avatarError}`, {
                defaultValue: t("errors.unknown_error"),
              })}
            </p>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="display_name">{t("profile.displayName")}</Label>
          <Counter value={displayName} max={MAX_NAME} />
        </div>
        <Input
          id="display_name"
          value={displayName}
          aria-invalid={length(displayName) > MAX_NAME}
          onChange={(e) => setDisplayName(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="username">{t("profile.username")}</Label>
        <div className="flex items-center gap-2">
          <span aria-hidden="true">@</span>
          <Input
            id="username"
            autoCapitalize="none"
            autoComplete="off"
            value={username}
            aria-invalid={usernameError !== null}
            aria-describedby={usernameError ? "username-error" : undefined}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        {usernameError && (
          <p id="username-error" className="text-destructive text-sm">
            {t(`errors.${usernameError}`)}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="bio">{t("profile.bio")}</Label>
          <Counter value={bio} max={MAX_BIO} />
        </div>
        <Textarea
          id="bio"
          value={bio}
          aria-invalid={length(bio) > MAX_BIO}
          onChange={(e) => setBio(e.target.value)}
        />
      </div>
      <fieldset className="flex flex-col gap-4 rounded-md border p-4">
        <legend className="px-1 text-sm font-medium">
          {t("profile.private")}
        </legend>
        <p className="text-muted-foreground text-sm">
          {t("profile.privateHelp")}
        </p>
        <div className="flex flex-col gap-2">
          <Label htmlFor="birthday">{t("profile.birthday")}</Label>
          <Input
            id="birthday"
            type="date"
            min="1900-01-01"
            value={birthday}
            onChange={(e) => setBirthday(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="phone">{t("profile.phone")}</Label>
          <Input
            id="phone"
            type="tel"
            autoComplete="off"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>
      </fieldset>
      <DialogFooter>
        <Button type="submit" disabled={!canSave}>
          {update.isPending ? t("profile.saving") : t("profile.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function EditProfileDialog({ me, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{t("profile.edit")}</DialogTitle>
          <DialogDescription className="sr-only">
            {t("profile.editDescription")}
          </DialogDescription>
        </DialogHeader>
        <EditProfileForm me={me} onOpenChange={onOpenChange} />
      </DialogContent>
    </Dialog>
  );
}
