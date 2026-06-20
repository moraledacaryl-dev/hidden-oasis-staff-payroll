import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { AnnualReviewForm } from "@/components/AnnualReviewForm";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { apiBaseUrl } from "@/lib/api";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";

function defaultYear() {
  return new Date().getFullYear();
}

async function authHeaders(): Promise<HeadersInit> {
  const token = (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value;
  return {
    Accept: "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(process.env.STAFF_PAYROLL_API_KEY ? { "X-API-Key": process.env.STAFF_PAYROLL_API_KEY } : {}),
  };
}

async function loadAnnualReviews(year: number) {
  const response = await fetch(`${apiBaseUrl()}/api/v1/performance/annual-reviews?year=${year}`, {
    headers: await authHeaders(),
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    return { ok: false, year, items: [], error: `Annual review API failed ${response.status}: ${text}` };
  }
  return response.json();
}

export default async function PerformanceReviewsPage({
  searchParams,
}: {
  searchParams: Promise<{ year?: string; employee?: string }>;
}) {
  const session = await currentSession();
  if (!session) redirect("/login");

  if (!["owner", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;
  }

  const params = await searchParams;
  const year = Number(params.year || defaultYear());
  const employeeFilter = (params.employee || "").trim().toLowerCase();
  const data = await loadAnnualReviews(year);
  const items = (data.items || []).filter((item: any) => {
    if (!employeeFilter) return true;
    return String(item.employee?.full_name || "").toLowerCase().includes(employeeFilter);
  });

  const draftCount = items.filter((item: any) => !item.review || item.review.status === "Draft").length;
  const submittedCount = items.filter((item: any) => item.review?.status === "Submitted").length;
  const finalizedCount = items.filter((item: any) => item.review?.status === "Finalized").length;

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Performance Reviews</span>
            <h1>Annual Reviews {year}</h1>
            <p className="muted">Structured yearly staff reviews. This is separate from memos and attendance discipline.</p>
          </div>
          <StatusBadge label={`${finalizedCount} finalized`} tone={finalizedCount ? "ok" : "neutral"} />
        </header>

        <form className="card" action="/performance-reviews">
          <div className="form-grid">
            <label>Year<input name="year" type="number" min="2024" max="2100" defaultValue={year} /></label>
            <label>Staff search<input name="employee" placeholder="Search employee name" defaultValue={params.employee || ""} /></label>
          </div>
          <div className="badge-row"><button className="primary-button" type="submit">View reviews</button></div>
        </form>

        {!data.ok ? (
          <section className="card">
            <strong>Annual reviews did not load.</strong>
            <p className="muted">{data.error || "The review API returned an error."}</p>
          </section>
        ) : null}

        <section className="grid cols-3">
          <div className="card"><strong>{draftCount}</strong><p className="muted">Not started / draft</p></div>
          <div className="card"><strong>{submittedCount}</strong><p className="muted">Submitted</p></div>
          <div className="card"><strong>{finalizedCount}</strong><p className="muted">Finalized</p></div>
        </section>

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>Employee Reviews</h2>
              <p className="muted">Supervisor can see previous comments while writing the current annual review.</p>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Status</th>
                  <th>Overall</th>
                  <th>Previous comments</th>
                  <th>Current comments</th>
                  <th>Review</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item: any) => (
                  <tr key={item.employee.id}>
                    <td>
                      <strong>{item.employee.full_name}</strong>
                      <br />
                      <span className="muted">{item.employee.employee_code || "—"} · {item.employee.department || "—"} · {item.employee.position || "—"}</span>
                    </td>
                    <td>{item.review?.status || "Not started"}</td>
                    <td>{item.review?.overall_rating ? `${item.review.overall_rating}/5` : "—"}</td>
                    <td>
                      {(item.previous_reviews || []).length ? (
                        (item.previous_reviews || []).map((previous: any) => (
                          <div key={previous.id} className="muted">
                            <strong>{previous.review_year}</strong>: {previous.strengths || previous.improvements || previous.supervisor_recommendation || "No comment"}
                          </div>
                        ))
                      ) : (
                        <span className="muted">No previous comments</span>
                      )}
                    </td>
                    <td>
                      {item.review?.strengths ? <div><strong>Positive:</strong> {item.review.strengths}</div> : null}
                      {item.review?.improvements ? <div><strong>Improve:</strong> {item.review.improvements}</div> : null}
                      {!item.review?.strengths && !item.review?.improvements ? <span className="muted">—</span> : null}
                    </td>
                    <td>
                      <AnnualReviewForm
                        employee={item.employee}
                        review={item.review}
                        previousReviews={item.previous_reviews || []}
                        reviewYear={year}
                        canFinalize={session.role_key === "owner"}
                      />
                    </td>
                  </tr>
                ))}
                {items.length === 0 ? <tr><td colSpan={6}>No employees found.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}
