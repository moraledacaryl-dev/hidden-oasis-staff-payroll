import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { AnnualReviewForm } from "@/components/AnnualReviewForm";
import { PerformanceLogForm } from "@/components/PerformanceLogForm";
import { Shell } from "@/components/Shell";
import { apiBaseUrl } from "@/lib/api";
import { ACCESS_TOKEN_COOKIE } from "@/lib/session-client";
import { currentSession } from "@/lib/session";

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

  if (!response.ok) return { ok: false, items: [] };
  return response.json();
}

async function loadLogs(employeeId: number, year: number) {
  const response = await fetch(`${apiBaseUrl()}/api/v1/performance/logs?employee_id=${employeeId}&year=${year}`, {
    headers: await authHeaders(),
    cache: "no-store",
  });

  if (!response.ok) return { ok: false, items: [] };
  return response.json();
}

export default async function EmployeePerformancePage({
  params,
  searchParams,
}: {
  params: Promise<{ employeeId: string }>;
  searchParams: Promise<{ year?: string }>;
}) {
  const session = await currentSession();
  if (!session) redirect("/login");

  if (!["owner", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;
  }

  const resolvedParams = await params;
  const resolvedSearch = await searchParams;
  const employeeId = Number(resolvedParams.employeeId);
  const year = Number(resolvedSearch.year || new Date().getFullYear());

  const [reviewsData, logsData] = await Promise.all([
    loadAnnualReviews(year),
    loadLogs(employeeId, year),
  ]);

  const item = (reviewsData.items || []).find((row: any) => Number(row.employee?.id) === employeeId);

  if (!item) {
    return (
      <Shell allowedRoles={["owner", "supervisor"]}>
        <div className="page review-page">
          <Link className="primary-link" href={`/performance-reviews?year=${year}`}>Back</Link>
          <section className="card">Employee not found.</section>
        </div>
      </Shell>
    );
  }

  const employee = item.employee;
  const logs = logsData.items || [];
  const currentMonth = new Date().toISOString().slice(0, 7);

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page review-page">
        <section className="review-toolbar">
          <Link className="primary-link" href={`/performance-reviews?year=${year}`}>Back to reviews</Link>
          <Link className="primary-link" href={`/attendance?month=${currentMonth}&employee=${encodeURIComponent(employee.full_name || "")}`}>View attendance</Link>
        </section>

        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Performance Review</span>
            <h1>{employee.full_name}</h1>
            <p className="muted">{employee.employee_code || "—"} · {employee.department || "—"} · {employee.position || "—"} · {year}</p>
          </div>
        </header>

        <section className="review-two-col">
          <div className="review-side">
            <PerformanceLogForm employeeId={employeeId} />

            <section className="card">
              <div className="panel-title">
                <div>
                  <h2>This year’s performance notes</h2>
                  <p className="muted">Supervisor notes used as context for the annual review.</p>
                </div>
              </div>

              <div className="review-log-list">
                {logs.map((log: any) => (
                  <article key={log.id} className="review-log-card">
                    <div className="review-log-meta">
                      <span className="badge">{log.log_date}</span>
                      <span className={log.category === "Concern" ? "badge warning" : log.category === "Positive" ? "badge ok" : "badge"}>
                        {log.category}{Number(log.is_general || 0) ? " · General" : ""}
                      </span>
                      <span className="badge">{log.area}</span>
                      <span className={log.severity === "High" ? "badge danger" : log.severity === "Medium" ? "badge warning" : "badge"}>
                        {log.severity}
                      </span>
                    </div>
                    <div className="review-log-note"><strong>{log.note}</strong></div>
                    {log.private_note ? <span className="muted">Private: {log.private_note}</span> : null}
                    {log.evidence_ref ? <span className="muted">Evidence: {log.evidence_ref}</span> : null}
                    <span className="muted">Logged by {log.created_by || "—"}</span>
                  </article>
                ))}
                {logs.length === 0 ? <p className="footer-note">No performance notes yet.</p> : null}
              </div>
            </section>
          </div>

          <section className="card">
            <div className="panel-title">
              <div>
                <h2>Annual Review</h2>
                <p className="muted">Previous comments are shown inside the review form.</p>
              </div>
            </div>

            <AnnualReviewForm
              employee={employee}
              review={item.review}
              previousReviews={item.previous_reviews || []}
              reviewYear={year}
              canFinalize={session.role_key === "owner"}
            />
          </section>
        </section>
      </div>
    </Shell>
  );
}
