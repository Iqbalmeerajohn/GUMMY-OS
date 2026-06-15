import { LivingOrb } from "@/components/brand/LivingOrb";
import { cn } from "@/lib/utils";

/** One message row. GUMMY (assistant) is anchored by the orb; user is plain. */
export function MessageBubble({
  role,
  content,
  thinking = false,
}: {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  thinking?: boolean;
}) {
  const isUser = role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="bg-accent text-accent-foreground max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 text-sm whitespace-pre-wrap">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <LivingOrb
        size={28}
        state={thinking ? "thinking" : "idle"}
        className="mt-0.5 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <span className="text-muted-foreground mb-1 block text-xs font-medium">
          GUMMY
        </span>
        <div
          className={cn(
            "text-sm leading-relaxed whitespace-pre-wrap",
            thinking && "text-muted-foreground",
          )}
        >
          {thinking ? "Thinking…" : content}
        </div>
      </div>
    </div>
  );
}
