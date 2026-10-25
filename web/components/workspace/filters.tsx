/** A row of filters that submit as a GET form, so every filtered view has its own link. */
export function Filters({
  fields,
  values,
  total,
  shown,
}: {
  fields: {
    name: string;
    label: string;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }[];
  values: Record<string, string | undefined>;
  total: number;
  shown: number;
}) {
  return (
    <form method="get" className="no-print mb-5 flex flex-wrap items-end gap-3">
      {fields.map((f) => (
        <div key={f.name} className="min-w-40 flex-1 sm:flex-none">
          <label htmlFor={`f-${f.name}`} className="label">
            {f.label}
          </label>
          {f.options ? (
            <select id={`f-${f.name}`} name={f.name} defaultValue={values[f.name] ?? ""} className="field">
              <option value="">All</option>
              {f.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              id={`f-${f.name}`}
              name={f.name}
              defaultValue={values[f.name] ?? ""}
              placeholder={f.placeholder}
              className="field"
            />
          )}
        </div>
      ))}
      <button className="button button-solid">Filter</button>
      <a href="?" className="link text-sm">
        Clear
      </a>
      <span className="text-faint ml-auto text-sm">
        {shown} of {total} shown
      </span>
    </form>
  );
}
