"use client";

import { TriangleAlert } from "lucide-react";
import { useState } from "react";

import { CodeBlock, CopyField } from "@/components/copy-field";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { snippetsFor } from "@/lib/snippets";
import { useSystemInfo } from "@/lib/queries";

/**
 * A key, shown once, with the snippets that connect a tool to the gateway using exactly this
 * key. The page never has the key again: it is stored only as a keyed hash.
 */
export function KeyReveal({ secret }: { secret: string }) {
  const system = useSystemInfo();
  const [tab, setTab] = useState("cli");
  const snippets = snippetsFor(system.data?.gateway_url ?? "http://localhost:8150/mcp", secret);
  return (
    <div className="space-y-3">
      <div className="bg-warning-soft text-warning flex items-start gap-2 rounded-lg px-3 py-2.5 text-[13px]">
        <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p>Copy this key now. It is shown only once and cannot be recovered; create a new key if you lose it.</p>
      </div>
      <CopyField value={secret} label="API key" />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList aria-label="Connection snippets">
          {snippets.map((snippet) => (
            <TabsTrigger key={snippet.id} value={snippet.id}>
              {snippet.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {snippets.map((snippet) => (
          <TabsContent key={snippet.id} value={snippet.id} className="pt-3">
            <CodeBlock code={snippet.code} label={`${snippet.label} snippet`} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
