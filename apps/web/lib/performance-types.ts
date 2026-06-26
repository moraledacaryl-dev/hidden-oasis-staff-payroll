export type PerformanceEmployee = {
  id: number;
  full_name: string;
  employee_code?: string | null;
  department?: string | null;
  position?: string | null;
};

export type AnnualReview = {
  id: number;
  review_year: number;
  status: string;
  final_result?: string | null;
  overall_rating?: number | null;
  strengths?: string | null;
  improvements?: string | null;
  notable_events?: string | null;
  training_needed?: string | null;
  supervisor_recommendation?: string | null;
  attendance_rating?: number | null;
  work_quality_rating?: number | null;
  reliability_rating?: number | null;
  teamwork_rating?: number | null;
  customer_service_rating?: number | null;
  initiative_rating?: number | null;
  sop_rating?: number | null;
  communication_rating?: number | null;
};

export type AnnualReviewItem = {
  employee: PerformanceEmployee;
  review: AnnualReview | null;
  previous_reviews: AnnualReview[];
};

export type PerformanceLog = {
  id: number;
  log_date: string;
  category: string;
  area: string;
  severity: string;
  note: string;
  private_note?: string | null;
  evidence_ref?: string | null;
  created_by?: string | null;
  is_general?: number;
};
