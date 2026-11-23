"use client";

import { useState } from "react";

import { CodeBlock, CopyField } from "@/components/copy-field";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSystemInfo } from "@/lib/queries";
import { snippetsFor } from "@/lib/snippets";
import type { Client } from "@/lib/types";

/** How to point a tool at the gateway as this client (the key is created on the Keys tab). */
export function ConnectPanel({ client }: { client: Client }) {
  const system = useSystemInfo();
  const [tab, setTab] = useState("cli");
  const url = system.data?.gateway_url ?? "http://localhost:8150/mcp";
  const snippets = snippetsFor(url);
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Gateway endpoint</CardTitle>
            <CardDescription>
              One URL for every tool {client.name} may use. Authenticate with one of its keys.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <CopyField value={url} label="Gateway endpoint" />
          <p className="text-muted-foreground mt-3 text-[13px]">
            Tools are named {client.tool_separator === "." ? "server.tool" : "server__tool"}. Replace{" "}
            <code className="font-mono">mch_YOUR_KEY</code> with a key from the Keys tab.
          </p>
        </CardContent>
      </Card>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList aria-label="Connection snippets">
          {snippets.map((snippet) => (
            <TabsTrigger key={snippet.id} value={snippet.id}>
              {snippet.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {snippets.map((snippet) => (
          <TabsContent key={snippet.id} value={snippet.id}>
            <CodeBlock code={snippet.code} label={`${snippet.label} snippet`} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
