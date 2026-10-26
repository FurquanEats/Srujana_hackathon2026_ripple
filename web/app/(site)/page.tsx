import { DitherEdge } from "@/components/dither-edge";
import { GridLines } from "@/components/grid-lines";
import { SiteHeader } from "@/components/site-header";

import { CallToAction } from "./sections/call-to-action";
import { Fair } from "./sections/fair";
import { Gap } from "./sections/gap";
import { Hero } from "./sections/hero";
import { HowItWorks } from "./sections/how-it-works";
import { Rules } from "./sections/rules";
import { Security } from "./sections/security";
import { Showcase } from "./sections/showcase";
import { SiteFooter } from "./sections/site-footer";
import { TraceYourself } from "./sections/trace-yourself";

/** Dark and light sections alternate as on the reference site, with a pixel-dither edge at each change. */
export default function HomePage() {
  return (
    <>
      <SiteHeader />
      <main>
        <div className="tone-dark relative isolate">
          <GridLines />
          <Hero />
        </div>
        <DitherEdge to="paper" />
        <div className="tone-light relative isolate">
          <GridLines />
          <Gap />
          <HowItWorks />
        </div>
        <DitherEdge to="ink" />
        <div className="tone-dark relative isolate">
          <GridLines />
          <Showcase />
          <TraceYourself />
        </div>
        <DitherEdge to="paper" />
        <div className="tone-light relative isolate">
          <GridLines />
          <Fair />
          <Rules />
          <Security />
        </div>
        <DitherEdge to="ink" />
        <div className="tone-dark relative isolate">
          <GridLines />
          <CallToAction />
          <SiteFooter />
        </div>
      </main>
    </>
  );
}
