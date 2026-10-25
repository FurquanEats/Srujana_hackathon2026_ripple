/** Four thin full-height lines that divide the home page into columns, behind everything else. */
export function GridLines() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 mx-auto flex max-w-[1440px] justify-evenly"
    >
      {[0, 1, 2, 3].map((i) => (
        <span key={i} className="h-full w-px bg-white/[0.08]" />
      ))}
    </div>
  );
}
