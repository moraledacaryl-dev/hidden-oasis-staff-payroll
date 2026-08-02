export type ScheduleShift = {
  id: number;
  employee_id: number | null;
  shift_date: string;
  start_time: string;
  end_time: string;
  position: string;
  department?: string | null;
  employee_department?: string | null;
  break_minutes: number;
  status: string;
  notes?: string | null;
  employee_name?: string | null;
  planned_paid_hours: number;
  is_overnight: boolean;
  source?: string;
  movable?: boolean;
  actual_in?: string | null;
  actual_out?: string | null;
  actual_status?: string | null;
  actual_source?: string | null;
  actual_notes?: string | null;
  is_absent?: number | null;
  absence_type?: string | null;
  approved_ot_hours?: number | null;
};

export type ScheduleEmployee = {
  id: number;
  full_name: string;
  employee_code?: string;
  department?: string;
  position?: string;
  default_shift_start?: string | null;
  default_shift_end?: string | null;
  unpaid_break_minutes?: number | null;
};

export type ScheduleActual = {
  id: number;
  scheduled_shift_id?: number | null;
  employee_id: number;
  work_date: string;
  actual_in?: string | null;
  actual_out?: string | null;
  attendance_status?: string | null;
  approved_ot_hours?: number | null;
  is_absent?: number | null;
  absence_type?: string | null;
  source?: string | null;
  verification_type?: string | null;
  notes?: string | null;
  employee_name?: string | null;
};

export type ScheduleRestDay = {
  id: number;
  employee_id: number;
  work_date: string;
  notes?: string | null;
};

export type ScheduleLeaveStatus = {
  id: number;
  employee_id: number;
  work_date: string;
  leave_type_name: string;
  paid: number;
  status: string;
  reason?: string | null;
};
