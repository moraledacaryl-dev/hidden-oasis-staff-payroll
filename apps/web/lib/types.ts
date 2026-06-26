export type ApiMeta = {
  app: string;
  api_version: string;
  database_path: string;
  database_exists: boolean;
  table_count: number;
  employee_count: number;
  payroll_run_count: number;
  mode: string;
};

export type Employee = {
  id: number;
  employee_code: string;
  full_name: string;
  department_id: number | null;
  department_name: string | null;
  position: string | null;
  employment_type: string | null;
  status: string;
  default_shift_start: string | null;
  default_shift_end: string | null;
  standard_shift_hours: number | null;
  unpaid_break_minutes: number | null;
  benefits_sss: number;
  benefits_philhealth: number;
  benefits_pagibig: number;
  benefits_tax: number;
  created_at: string;
};

export type PayrollCheck = {
  severity: "Blocker" | "Warning" | string;
  category: string;
  issue: string;
  count: number | string;
  recommended_action: string;
};

export type PayrollPreviewItem = {
  employee_id: number;
  employee_code: string;
  full_name: string;
  regular_hours: number;
  regular_pay: number;
  approved_ot_hours: number;
  ot_pay: number;
  night_diff_hours: number;
  night_diff_pay: number;
  holiday_pay: number;
  paid_leave_days: number;
  paid_leave_pay: number;
  freelance_pay: number;
  other_earnings: number;
  gross_pay: number;
  late_minutes: number;
  undertime_minutes: number;
  unpaid_absence_days: number;
  sss_ee: number;
  philhealth_ee: number;
  pagibig_ee: number;
  sss_er: number;
  sss_ec: number;
  philhealth_er: number;
  pagibig_er: number;
  tax: number;
  cash_advance_deduction: number;
  other_deductions: number;
  total_deductions: number;
  net_pay: number;
  warnings: string[];
};

export type PayrollPreview = {
  period_start: string;
  period_end: string;
  summary: string;
  checks: PayrollCheck[];
  totals: {
    employees: number;
    gross_pay: number;
    net_pay: number;
    total_deductions: number;
    cash_advance_deduction: number;
  };
  items: PayrollPreviewItem[];
  mode: "preview_only_no_save" | string;
};

export type RoleKey = "owner" | "payroll" | "supervisor" | "staff";
