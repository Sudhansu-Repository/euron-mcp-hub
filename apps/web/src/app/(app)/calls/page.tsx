import { Suspense } from "react";

import { CallsView } from "@/components/calls/calls-view";

export default function CallsPage() {
  return (
    <Suspense>
      <CallsView />
    </Suspense>
  );
}
