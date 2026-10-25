import { Suspense } from "react";

import { LoadingPanel } from "@/components/ui";

import { Workbench } from "./Workbench";

export default function CasePage() {
  return (
    <Suspense fallback={<LoadingPanel label="Loading case…" />}>
      <Workbench />
    </Suspense>
  );
}
