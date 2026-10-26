/**
 * Four thin full-height lines that divide a home page section into columns. Each section draws its own, behind its
 * content (a negative layer inside the section's isolated stacking context), in that section's line colour.
 */
export function GridLines() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 -z-10 mx-auto flex max-w-[1440px] justify-evenly"
    >
      {[0, 1, 2, 3].map((i) => (
        <span key={i} className="h-full w-px bg-[var(--line)]" />
      ))}
    </div>
  );
}
