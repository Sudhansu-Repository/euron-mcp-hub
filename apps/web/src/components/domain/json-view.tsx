import { cn } from "@/lib/cn";

/** Pretty-printed JSON on the code surface, scrolling inside its own box. */
export function JsonView({ value, label, className }: { value: unknown; label: string; className?: string }) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <pre
      aria-label={label}
      tabIndex={0}
      className={cn(
        "bg-code border-border scroll-quiet max-h-96 overflow-auto rounded-lg border p-3 font-mono text-[12px] leading-relaxed break-words whitespace-pre-wrap",
        className,
      )}
    >
      {text}
    </pre>
  );
}
