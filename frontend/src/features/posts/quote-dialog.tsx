import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Composer } from "./composer";
import type { Post } from "./types";

export function QuoteDialog({
  post,
  open,
  onOpenChange,
}: {
  post: Post;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")} className="p-0">
        <DialogHeader className="px-6 pt-6">
          <DialogTitle>{t("posts.quoteTitle")}</DialogTitle>
          <DialogDescription className="sr-only">
            {t("posts.quoteTitle")}
          </DialogDescription>
        </DialogHeader>
        <Composer quoteOf={post} onPosted={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
