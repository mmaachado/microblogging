import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

interface Props {
  avatarUrl: string | null;
  name: string;
  className?: string;
}

export function ProfileAvatar({ avatarUrl, name, className }: Props) {
  return (
    <Avatar className={cn("size-24", className)}>
      {avatarUrl && <AvatarImage src={avatarUrl} alt="" />}
      <AvatarFallback className="text-2xl uppercase">
        {name.charAt(0)}
      </AvatarFallback>
    </Avatar>
  );
}
