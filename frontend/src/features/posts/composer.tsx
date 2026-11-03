import { ImagePlus, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/features/auth/use-auth";
import { BodyCounter } from "./body-counter";
import { MAX_BODY, bodyLength } from "./body";
import { useCreatePost } from "./use-posts";

const MAX_FILES = 4;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_VIDEO_BYTES = 50 * 1024 * 1024;
const ACCEPT =
  "image/jpeg,image/png,image/webp,image/gif,video/mp4,video/webm,video/quicktime";
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const VIDEO_TYPES = ["video/mp4", "video/webm", "video/quicktime"];

interface Attachment {
  file: File;
  url: string;
}

const isVideo = (file: File) => VIDEO_TYPES.includes(file.type);

function checkFiles(files: File[]): string | null {
  if (files.some((f) => !IMAGE_TYPES.includes(f.type) && !isVideo(f))) {
    return "invalid_media";
  }
  const videos = files.filter(isVideo).length;
  if (videos > 0 && videos < files.length) return "mixed_media";
  if (videos > 1 || files.length > MAX_FILES) return "too_many_files";
  const tooBig = files.some(
    (f) => f.size > (isVideo(f) ? MAX_VIDEO_BYTES : MAX_IMAGE_BYTES),
  );
  return tooBig ? "file_too_large" : null;
}

export function Composer() {
  const { t } = useTranslation();
  const create = useCreatePost();
  const input = useRef<HTMLInputElement>(null);
  const [body, setBody] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const urls = useRef<string[]>([]);

  useEffect(
    () => () => {
      urls.current.forEach((url) => URL.revokeObjectURL(url));
    },
    [],
  );

  function revoke(url: string) {
    URL.revokeObjectURL(url);
    urls.current = urls.current.filter((u) => u !== url);
  }

  function onPick(picked: File[]) {
    const error = checkFiles([...attachments.map((a) => a.file), ...picked]);
    setFileError(error);
    if (error) return;
    const added = picked.map((file) => {
      const url = URL.createObjectURL(file);
      urls.current.push(url);
      return { file, url };
    });
    setAttachments((current) => [...current, ...added]);
  }

  function remove(attachment: Attachment) {
    revoke(attachment.url);
    setAttachments((current) => current.filter((a) => a !== attachment));
    setFileError(null);
  }

  const over = bodyLength(body) > MAX_BODY;
  const empty = body.trim() === "" && attachments.length === 0;
  const disabled = create.isPending || over || empty;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (disabled) return;
    create.mutate(
      { body, files: attachments.map((a) => a.file) },
      {
        onSuccess: () => {
          attachments.forEach((a) => revoke(a.url));
          setAttachments([]);
          setBody("");
          setFileError(null);
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3 border-b p-4">
      <Textarea
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder={t("posts.placeholder")}
        aria-label={t("posts.placeholder")}
        aria-invalid={over}
      />
      {attachments.length > 0 && (
        <ul className="grid grid-cols-2 gap-2">
          {attachments.map((attachment, index) => (
            <li key={attachment.url} className="relative">
              {isVideo(attachment.file) ? (
                <video
                  src={attachment.url}
                  aria-label={t("posts.preview", { n: index + 1 })}
                  muted
                  className="max-h-48 w-full rounded-md object-cover"
                />
              ) : (
                <img
                  src={attachment.url}
                  alt={t("posts.preview", { n: index + 1 })}
                  className="max-h-48 w-full rounded-md object-cover"
                />
              )}
              <Button
                type="button"
                variant="secondary"
                size="icon-xs"
                className="absolute top-1 right-1"
                aria-label={t("posts.removeMedia")}
                onClick={() => remove(attachment)}
              >
                <X />
              </Button>
            </li>
          ))}
        </ul>
      )}
      {(fileError || create.isError) && (
        <Alert variant="destructive">
          <AlertDescription>
            {fileError
              ? t(`errors.${fileError}`)
              : errorMessage(t, create.error)}
          </AlertDescription>
        </Alert>
      )}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <input
            ref={input}
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            onChange={(event) => {
              onPick(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={t("posts.attach")}
            onClick={() => input.current?.click()}
          >
            <ImagePlus />
          </Button>
          <BodyCounter value={body} />
        </div>
        <Button type="submit" disabled={disabled}>
          {t(create.isPending ? "posts.submitting" : "posts.submit")}
        </Button>
      </div>
    </form>
  );
}
