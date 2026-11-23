import { KeyRound, ScrollText, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

import { Wordmark } from "@/components/brand";
import { ThemeMenu } from "@/components/shell/theme-menu";

const FEATURES = [
  {
    icon: ShieldCheck,
    title: "Permissions per client",
    text: "Each agent sees only the tools its policy allows, with constraints on the arguments it may pass.",
  },
  {
    icon: KeyRound,
    title: "Secrets stay secret",
    text: "Upstream tokens are encrypted with KMS, injected when the gateway connects, and never shown again.",
  },
  {
    icon: ScrollText,
    title: "Every call on the record",
    text: "Who called which tool, with what, how long it took and why a call was refused.",
  },
];

/** Decorative: one endpoint, tools from several servers, and what a client may use. */
function GatewaySample() {
  const rows = [
    { name: "tickets.list_tickets", allowed: true },
    { name: "tickets.create_ticket", allowed: true },
    { name: "tickets.delete_ticket", allowed: false },
    { name: "notes.search_notes", allowed: true },
  ];
  return (
    <div aria-hidden className="relative mt-8 rounded-2xl border border-white/15 bg-white/[0.07] p-4 backdrop-blur-sm">
      <p className="text-[11px] font-medium tracking-wider text-white/60 uppercase">support-copilot, one endpoint</p>
      <ul className="mt-3 space-y-1.5">
        {rows.map((row) => (
          <li key={row.name} className="flex items-center justify-between rounded-lg bg-black/25 px-3 py-1.5">
            <span className="font-mono text-[12px] text-white/90">{row.name}</span>
            <span
              className={
                row.allowed
                  ? "rounded bg-emerald-400/20 px-1.5 py-0.5 text-[11px] text-emerald-200"
                  : "rounded bg-rose-400/20 px-1.5 py-0.5 text-[11px] text-rose-200"
              }
            >
              {row.allowed ? "allowed" : "denied"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The split layout of the sign-in and first-run pages: a brand panel on large screens, the
 * form column everywhere. Children are the form.
 */
export function AuthLayout({ productName, children }: { productName: string; children: ReactNode }) {
  return (
    <main className="grid min-h-dvh lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      <section className="relative hidden overflow-hidden bg-[#0d0f2e] p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(60% 50% at 10% 0%, rgb(99 102 241 / 0.5), transparent 70%), radial-gradient(50% 45% at 100% 100%, rgb(45 212 191 / 0.18), transparent 70%)",
          }}
        />
        <Wordmark name={productName} className="relative [&_span]:text-white" />
        <div className="relative max-w-md">
          <h2 className="text-[34px] leading-tight font-semibold tracking-tight">
            One front door for every MCP server.
          </h2>
          <p className="mt-3 text-[15px] text-white/75">
            Register your servers once. Give each agent one URL and one key, and decide exactly which tools it may call.
          </p>
          <GatewaySample />
          <ul className="mt-8 space-y-4">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/10">
                  <Icon className="size-4" aria-hidden />
                </span>
                <span>
                  <span className="block text-sm font-medium">{title}</span>
                  <span className="block text-[13px] text-white/70">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-white/60">Open source under the MIT License.</p>
      </section>
      <section className="relative flex items-center justify-center p-6 sm:p-12">
        <div className="absolute top-4 right-4">
          <ThemeMenu />
        </div>
        <div className="w-full max-w-sm">
          <Wordmark name={productName} className="mb-10 lg:hidden" />
          {children}
        </div>
      </section>
    </main>
  );
}
