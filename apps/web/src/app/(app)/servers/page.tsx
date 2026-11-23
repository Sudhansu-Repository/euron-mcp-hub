import { Suspense } from "react";

import { ServersView } from "@/components/servers/servers-view";

export default function ServersPage() {
  return (
    <Suspense>
      <ServersView />
    </Suspense>
  );
}
