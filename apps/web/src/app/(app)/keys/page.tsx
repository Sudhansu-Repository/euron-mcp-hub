import { Suspense } from "react";

import { KeysView } from "@/components/keys/keys-view";

export default function KeysPage() {
  return (
    <Suspense>
      <KeysView />
    </Suspense>
  );
}
