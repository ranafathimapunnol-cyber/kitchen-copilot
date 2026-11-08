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
};

export type ColumnConfig = {
  key: string;
  label: string;
};

export type ResourceConfig = {
  title: string;
  description: string;
  endpoint: string;
  fields: FieldConfig[];
  columns: ColumnConfig[];
};
