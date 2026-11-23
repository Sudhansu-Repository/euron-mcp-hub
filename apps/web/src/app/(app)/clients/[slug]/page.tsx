"use client";

import { Suspense, use } from "react";

import { ClientDetail } from "@/components/clients/client-detail";

export default function ClientPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <Suspense>
      <ClientDetail slug={slug} />
    </Suspense>
  );
}
