/** A laptop drawn in CSS, for showing the workspace on the home page. */
export function LaptopFrame({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <figure className="mx-auto w-full max-w-5xl" aria-label={label}>
      <div className="rounded-t-[18px] border border-grey-700 bg-[#0b0b0b] p-[1.6%] shadow-[0_40px_120px_-30px_rgba(0,0,0,0.9)]">
        <div className="aspect-[16/10] overflow-hidden rounded-[6px] bg-ink">{children}</div>
      </div>
      <div className="relative mx-auto h-4 w-[106%] -translate-x-[2.8%] rounded-b-[14px] border border-t-0 border-grey-700 bg-gradient-to-b from-[#2a2a2a] to-[#151515]">
        <span className="absolute top-0 left-1/2 h-1.5 w-24 -translate-x-1/2 rounded-b-md bg-[#0e0e0e]" />
      </div>
    </figure>
  );
}
