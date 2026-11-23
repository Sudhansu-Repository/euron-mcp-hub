import { cn } from "@/lib/cn";

/** One hub, four spokes: every MCP server behind a single endpoint. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={cn("size-7", className)}>
      <rect width="64" height="64" rx="16" fill="var(--primary)" />
      <g stroke="var(--primary-foreground)" strokeWidth="3.5" strokeLinecap="round" opacity="0.85">
        <path d="M32 32 16 16M32 32l16-16M32 32 16 48M32 32l16 16" />
      </g>
      <g fill="var(--primary-foreground)">
        <circle cx="16" cy="16" r="4.5" />
        <circle cx="48" cy="16" r="4.5" />
        <circle cx="16" cy="48" r="4.5" />
        <circle cx="48" cy="48" r="4.5" />
        <circle cx="32" cy="32" r="8" />
      </g>
    </svg>
  );
}

export function Wordmark({ name, className }: { name: string; className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <BrandMark />
      <span className="text-[15px] font-semibold tracking-tight">{name}</span>
    </span>
  );
}
