"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { AnnualReview, PerformanceEmployee } from "@/lib/performance-types";

const ratingFields = [
  ["attendance_rating", "Attendance & punctuality"],
  ["work_quality_rating", "Work quality"],
  ["reliability_rating", "Reliability"],
  ["teamwork_rating", "Teamwork"],
  ["customer_service_rating", "Customer service"],
  ["initiative_rating", "Initiative"],
  ["sop_rating", "Following SOPs"],
  ["communication_rating", "Communication"],
  ["overall_rating", "Overall"],
] as const;

type Props = {
  employee: PerformanceEmployee;
  review: AnnualReview | null;
  previousReviews: AnnualReview[];
  reviewYear: number;
  canFinalize: boolean;
};

function value(review: AnnualReview | null, key: keyof AnnualReview, fallback: string | number = "") {
  return review?.[key] ?? fallback;
}

export function AnnualReviewForm({ employee, review, previousReviews, reviewYear, canFinalize }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage("");

    const body: Record<string, string | number | null> = {
      id: review?.id ?? null,
      employee_id: Number(employee.id),
      review_year: reviewYear,
      final_result: String(formData.get("final_result") || "Draft"),
      status: String(formData.get("status") || "Draft"),
      strengths: String(formData.get("strengths") || "") || null,
      improvements: String(formData.get("improvements") || "") || null,
      notable_events: String(formData.get("notable_events") || "") || null,
      training_needed: String(formData.get("training_needed") || "") || null,
      supervisor_recommendation: String(formData.get("supervisor_recommendation") || "") || null,
    };

    for (const [key] of ratingFields) {
      const raw = String(formData.get(key) || "");
      body[key] = raw ? Number(raw) : null;
    }

    const response = await fetch("/api/performance/annual-reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await response.json().catch(() => ({}));
    setBusy(false);

    if (!response.ok || !data.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "Annual review was not saved.");
      return;
    }

    setMessage("Saved.");
    setOpen(false);
    router.refresh();
  }

  if (!open) {
    return (
      <button className="primary-button" type="button" onClick={() => setOpen(true)}>
        {review ? "Edit review" : "Start review"}
      </button>
    );
  }

  return (
    <form action={submit} className="review-form">
      <strong>{employee.full_name}</strong>

      {previousReviews.length ? (
        <section className="action-item">
          <strong>Previous comments</strong>
          {previousReviews.map((previous) => (
            <div key={previous.id} className="grid" style={{ gap: 4, marginTop: 8 }}>
              <span className="muted">{previous.review_year} · {previous.final_result || "—"} · Overall {previous.overall_rating || "—"}/5</span>
              {previous.strengths ? <span><strong>Positive:</strong> {previous.strengths}</span> : null}
              {previous.improvements ? <span><strong>Needs improvement:</strong> {previous.improvements}</span> : null}
              {previous.supervisor_recommendation ? <span><strong>Recommendation:</strong> {previous.supervisor_recommendation}</span> : null}
            </div>
          ))}
        </section>
      ) : (
        <p className="muted">No previous review comments yet.</p>
      )}

      <div className="review-form-grid">
        {ratingFields.map(([key, label]) => (
          <label key={key}>
            {label}
            <select name={key} defaultValue={String(value(review, key, ""))}>
              <option value="">—</option>
              <option value="5">5 - Excellent</option>
              <option value="4">4 - Good</option>
              <option value="3">3 - Satisfactory</option>
              <option value="2">2 - Needs Improvement</option>
              <option value="1">1 - Unsatisfactory</option>
            </select>
          </label>
        ))}
      </div>

      <label>Strengths / positive observations<textarea name="strengths" rows={3} defaultValue={value(review, "strengths")} /></label>
      <label>Areas for improvement<textarea name="improvements" rows={3} defaultValue={value(review, "improvements")} /></label>
      <label>Notable incidents or achievements<textarea name="notable_events" rows={3} defaultValue={value(review, "notable_events")} /></label>
      <label>Training needed<textarea name="training_needed" rows={2} defaultValue={value(review, "training_needed")} /></label>
      <label>Manager recommendation<textarea name="supervisor_recommendation" rows={3} defaultValue={value(review, "supervisor_recommendation")} /></label>

      <div className="review-form-grid">
        <label>
          Final result
          <select name="final_result" defaultValue={value(review, "final_result", "Draft")}>
            <option>Draft</option>
            <option>Excellent</option>
            <option>Good</option>
            <option>Satisfactory</option>
            <option>Needs Improvement</option>
            <option>Unsatisfactory</option>
          </select>
        </label>
        <label>
          Status
          <select name="status" defaultValue={value(review, "status", "Draft")}>
            <option>Draft</option>
            <option>Submitted</option>
            {canFinalize ? <option>Finalized</option> : null}
          </select>
        </label>
      </div>

      <div className="badge-row">
        <button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving..." : "Save review"}</button>
        <button className="button ghost" type="button" onClick={() => setOpen(false)}>Cancel</button>
      </div>
      {message ? <p className="footer-note">{message}</p> : null}
    </form>
  );
}
