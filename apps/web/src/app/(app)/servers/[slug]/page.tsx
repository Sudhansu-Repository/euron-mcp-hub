"use client";

import { use } from "react";
import { Suspense } from "react";

import { ServerDetail } from "@/components/servers/server-detail";

export default function ServerPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <Suspense>
      <ServerDetail slug={slug} />
    </Suspense>
  );
}
