export type User = {
  id: number | string;
  email: string;
  full_name?: string | null;
  role: string;
  campus_id?: number | string;
};

export type SelectOption = {
  value: string;
  label: string;
};

export type FieldConfig = {
  name: string;
  label: string;
  type?: "text" | "email" | "number" | "textarea" | "select";
  required?: boolean;
  placeholder?: string;
  optionsEndpoint?: string;
  optionLabel?: string;
  options?: SelectOption[];
  /** A select field shown as a search-as-you-type list (Stage 7 S7-A). */
  searchable?: boolean;
};

export type ColumnConfig = {
  key: string;
  label: string;
  optionField?: string;
  /** Display labels for stored values, e.g. { RAW: "Raw" }. */
  labels?: Record<string, string>;
  /** Shown when the value is empty (instead of "—"). */
  emptyLabel?: string;
};

export type ResourceConfig = {
  title: string;
  description: string;
  endpoint: string;
  fields: FieldConfig[];
  columns: ColumnConfig[];
  /** An information note shown under the page header. */
  notice?: string;
};
