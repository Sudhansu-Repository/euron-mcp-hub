import { Suspense } from "react";

import { PlaygroundView } from "@/components/playground/playground-view";

export default function PlaygroundPage() {
  return (
    <Suspense>
      <PlaygroundView />
    </Suspense>
  );
}
