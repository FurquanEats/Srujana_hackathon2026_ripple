import type { Trail } from "@/lib/gateway/types";

import demoTrail from "./demo-trail.json";

/**
 * The PRD's demo story as the live gateway traced it (GET /v1/cases/{ack}/trail after
 * POST /v1/simulation/demo-story on `uv run ripple up`), shown in the home page's laptop.
 */
export const DEMO_TRAIL = demoTrail as Trail;
