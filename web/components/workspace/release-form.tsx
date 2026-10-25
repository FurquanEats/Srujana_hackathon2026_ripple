/** Record a lien lifted on a police or court order (SOP 11). The bank never lifts a CFCFRMS lien on its own. */
export function ReleaseForm({
  action,
  hidden,
  victimChoice,
  authority = "",
  submit = "Record the release",
}: {
  action: (form: FormData) => Promise<void>;
  hidden: Record<string, string>;
  victimChoice: boolean;
  authority?: string;
  submit?: string;
}) {
  return (
    <form action={action} className="grid gap-3 sm:grid-cols-2">
      {Object.entries(hidden).map(([k, v]) => (
        <input key={k} type="hidden" name={k} value={v} />
      ))}
      <div>
        <label className="label" htmlFor={`authority-${hidden.lien_id}`}>
          Ordered by (police station, officer or court)
        </label>
        <input
          id={`authority-${hidden.lien_id}`}
          name="authority"
          required
          minLength={3}
          maxLength={200}
          defaultValue={authority}
          className="field"
        />
      </div>
      <div>
        <label className="label" htmlFor={`order-${hidden.lien_id}`}>
          Order reference
        </label>
        <input
          id={`order-${hidden.lien_id}`}
          name="order"
          required
          minLength={3}
          maxLength={64}
          className="field font-mono"
          placeholder="CCPS/106/2026/41"
        />
      </div>
      <div className="sm:col-span-2">
        <label className="label" htmlFor={`reason-${hidden.lien_id}`}>
          Reason
        </label>
        <input
          id={`reason-${hidden.lien_id}`}
          name="reason"
          required
          minLength={5}
          maxLength={2000}
          className="field"
          defaultValue={victimChoice ? "" : "Interim custody to the victim under BNSS 106(3)"}
        />
      </div>
      {victimChoice && (
        <label className="flex gap-2 text-sm sm:col-span-2">
          <input
            type="checkbox"
            name="to_victim"
            defaultChecked
            className="mt-0.5 accent-[var(--color-accent)]"
          />
          The money goes back to the victim (not to the account holder)
        </label>
      )}
      <button className="button button-solid justify-self-start">{submit}</button>
    </form>
  );
}
