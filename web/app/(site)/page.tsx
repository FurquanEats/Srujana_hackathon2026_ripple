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

export default function HomePage() {
  return (
    <>
      <GridLines />
      <SiteHeader />
      <main>
        <Hero />
        <Gap />
        <HowItWorks />
        <DitherEdge to="paper" />
        <Fair />
        <DitherEdge to="ink" />
        <Rules />
        <Security />
        <Showcase />
        <CallToAction />
      </main>
      <SiteFooter />
    </>
  );
}
