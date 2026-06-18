import { LivingOrb } from "@/components/brand/LivingOrb";

/** One message row. GUMMY (assistant) is anchored by the orb; user is plain. */
export function MessageBubble({
  role,
  content,
  streaming = false,
  status = null,
  footer = null,
}: {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  /** Show a live typing cursor after the content (token streaming). */
  streaming?: boolean;
  /** Rendered in place of content before the first token arrives. */
  status?: React.ReactNode;
  /** Rendered under the assistant text (e.g. Memory Used, agent chip). */
  footer?: React.ReactNode;
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

  const showStatus = !content && status !== null;

  return (
    <div className="flex gap-3">
      <LivingOrb
        size={28}
        state={streaming || showStatus ? "thinking" : "idle"}
        className="mt-0.5 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <span className="text-muted-foreground mb-1 block text-xs font-medium">
          GUMMY
        </span>
        {showStatus ? (
          status
        ) : (
          <div className="text-sm leading-relaxed whitespace-pre-wrap">
            {content}
            {streaming ? (
              <span className="bg-primary ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse rounded-full align-middle" />
            ) : null}
          </div>
        )}
        {footer}
      </div>
    </div>
  );
}
