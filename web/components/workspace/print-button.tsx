"use client";

/** Prints the page; the print stylesheet hides the workspace's navigation. */
export function PrintButton({ label = "Print" }: { label?: string }) {
  return (
    <button type="button" onClick={() => window.print()} className="button button-ghost">
      {label}
    </button>
  );
}
