import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { QuotedPost } from "./types";

export function QuotedEmbed({ quote }: { quote: QuotedPost }) {
  const { t } = useTranslation();
  const { author } = quote;
  const [media] = quote.media;
  return (
    <Link
      to={`/post/${quote.id}`}
      className="hover:bg-accent/50 flex flex-col gap-1 rounded-lg border p-3"
    >
      <span className="flex flex-wrap items-baseline gap-x-2 text-sm">
        {author.display_name && (
          <span className="font-bold">{author.display_name}</span>
        )}
        <span className="text-muted-foreground">@{author.username}</span>
      </span>
      {quote.is_quote && (
        <span className="text-muted-foreground text-xs">
          {t("posts.quotingQuote")}
        </span>
      )}
      {quote.body && (
        <span className="break-words whitespace-pre-wrap">{quote.body}</span>
      )}
      {media &&
        (media.kind === "video" ? (
          <video
            src={media.url}
            aria-label={t("posts.mediaVideo")}
            preload="metadata"
            muted
            className="max-h-40 w-full rounded-md object-cover"
          />
        ) : (
          <img
            src={media.url}
            alt={t("posts.mediaAlt", { n: 1 })}
            loading="lazy"
            className="max-h-40 w-full rounded-md object-cover"
          />
        ))}
    </Link>
  );
}

export function QuoteUnavailable() {
  const { t } = useTranslation();
  return (
    <div className="text-muted-foreground rounded-lg border border-dashed p-3 text-sm">
      {t("posts.quoteUnavailable")}
    </div>
  );
}
