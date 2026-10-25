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
      <GridLines />
      <SiteHeader />
      <main>
        <div className="tone-dark">
          <Hero />
        </div>
        <DitherEdge to="paper" />
        <div className="tone-light">
          <Gap />
          <HowItWorks />
        </div>
        <DitherEdge to="ink" />
        <div className="tone-dark">
          <Showcase />
          <TraceYourself />
        </div>
        <DitherEdge to="paper" />
        <div className="tone-light">
          <Fair />
          <Rules />
          <Security />
        </div>
        <DitherEdge to="ink" />
        <div className="tone-dark">
          <CallToAction />
          <SiteFooter />
        </div>
      </main>
    </>
  );
}
