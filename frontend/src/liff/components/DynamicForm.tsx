import type { Jiaan1030FormField, Jiaan1030FormSection } from "../../api";

/** 依 fields_json schema 動態渲染輸入元件；payload 由呼叫端管理（debounce 存草稿）。 */
export function DynamicForm({
  sections,
  payload,
  onChange,
  disabled,
}: {
  sections: Jiaan1030FormSection[];
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const setField = (key: string, value: unknown) => onChange({ ...payload, [key]: value });

  return (
    <div className="stack">
      {sections.map((section) => (
        <div key={section.key} className="card stack">
          <h3>{section.label}</h3>
          {section.fields.map((field) => (
            <FormField key={field.key} field={field} value={payload[field.key]} disabled={disabled}
                      onChange={(v) => setField(field.key, v)} />
          ))}
        </div>
      ))}
    </div>
  );
}

function FormField({
  field,
  value,
  disabled,
  onChange,
}: {
  field: Jiaan1030FormField;
  value: unknown;
  disabled?: boolean;
  onChange: (value: unknown) => void;
}) {
  const label = (
    <label className="small">
      {field.label}
      {field.required ? <span className="tag warn">必填</span> : null}
    </label>
  );

  switch (field.type) {
    case "textarea":
      return (
        <div className="stack">
          {label}
          <textarea value={(value as string) ?? ""} disabled={disabled} maxLength={field.max_length ?? undefined}
                   onChange={(e) => onChange(e.target.value)} />
        </div>
      );
    case "select":
      return (
        <div className="stack">
          {label}
          <select value={(value as string) ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
            <option value="">請選擇</option>
            {(field.options ?? []).map((opt, i) => (
              <option key={opt} value={opt}>{field.option_labels?.[i] ?? opt}</option>
            ))}
          </select>
        </div>
      );
    case "radio":
      return (
        <div className="stack">
          {label}
          <div className="role-grid">
            {(field.options ?? []).map((opt) => (
              <button
                key={opt}
                type="button"
                className={`btn role-btn ${value === opt ? "primary" : ""}`}
                aria-pressed={value === opt}
                disabled={disabled}
                onClick={() => onChange(opt)}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
      );
    case "checkbox":
      return (
        <label className="small">
          <input type="checkbox" checked={Boolean(value)} disabled={disabled}
                onChange={(e) => onChange(e.target.checked)} /> {field.label}
        </label>
      );
    case "checkbox_group": {
      const selected = Array.isArray(value) ? (value as string[]) : [];
      const toggle = (opt: string) => {
        const next = selected.includes(opt) ? selected.filter((v) => v !== opt) : [...selected, opt];
        onChange(next);
      };
      return (
        <div className="stack">
          {label}
          <div className="role-grid">
            {(field.options ?? []).map((opt) => (
              <button
                key={opt}
                type="button"
                className={`btn role-btn ${selected.includes(opt) ? "primary" : ""}`}
                aria-pressed={selected.includes(opt)}
                disabled={disabled}
                onClick={() => toggle(opt)}
              >
                {selected.includes(opt) ? "✅ " : ""}{opt}
              </button>
            ))}
          </div>
        </div>
      );
    }
    case "date":
      return (
        <div className="stack">
          {label}
          <input type="date" value={(value as string) ?? ""} disabled={disabled}
                onChange={(e) => onChange(e.target.value)} />
        </div>
      );
    case "time":
      return (
        <div className="stack">
          {label}
          <input type="time" value={(value as string) ?? ""} disabled={disabled}
                onChange={(e) => onChange(e.target.value)} />
        </div>
      );
    case "number":
      return (
        <div className="stack">
          {label}
          <input type="number" value={(value as number | string) ?? ""} disabled={disabled}
                onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />
        </div>
      );
    case "signature_placeholder":
      return (
        <div className="notice warn small">
          {field.label}：簽章欄位尚未實作（需另行確認簽署流程與法規要求），目前僅佔位，不收集簽章資料。
        </div>
      );
    default:
      return (
        <div className="stack">
          {label}
          <input type="text" value={(value as string) ?? ""} disabled={disabled} maxLength={field.max_length ?? undefined}
                onChange={(e) => onChange(e.target.value)} />
        </div>
      );
  }
}
