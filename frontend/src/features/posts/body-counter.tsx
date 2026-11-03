import { cn } from "@/lib/utils";
import { MAX_BODY, bodyLength } from "./body";

const WARN_AT = 10;

export function BodyCounter({ value }: { value: string }) {
  const used = bodyLength(value);
  return (
    <span
      className={cn(
        "text-xs",
        MAX_BODY - used < WARN_AT ? "text-destructive" : "text-muted-foreground",
      )}
    >
      {used}/{MAX_BODY}
    </span>
  );
}
