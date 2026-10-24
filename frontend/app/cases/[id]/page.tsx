import { Suspense } from "react";

import { Workbench } from "./Workbench";

export default function CasePage() {
  return (
    <Suspense fallback={<p className="text-slate-400">Loading case…</p>}>
      <Workbench />
    </Suspense>
  );
}
