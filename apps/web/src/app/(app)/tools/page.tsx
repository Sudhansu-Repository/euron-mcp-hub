import { Suspense } from "react";

import { ToolsView } from "@/components/tools/tools-view";

export default function ToolsPage() {
  return (
    <Suspense>
      <ToolsView />
    </Suspense>
  );
}
