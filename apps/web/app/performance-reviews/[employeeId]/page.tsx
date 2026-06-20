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
        <div className="page">
          <Link className="primary-link" href={`/performance-reviews?year=${year}`}>Back</Link>
          <section className="card">Employee not found.</section>
        </div>
      </Shell>
    );
  }

  const employee = item.employee;
  const logs = logsData.items || [];

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page">
        <section className="badge-row">
          <Link className="primary-link" href={`/performance-reviews?year=${year}`}>Back to reviews</Link>
          <Link className="primary-link" href={`/attendance?month=${year}-06&employee=${encodeURIComponent(employee.full_name || "")}`}>View attendance</Link>
        </section>

        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Performance Review</span>
            <h1>{employee.full_name}</h1>
            <p className="muted">{employee.employee_code || "—"} · {employee.department || "—"} · {employee.position || "—"} · {year}</p>
          </div>
        </header>

        <PerformanceLogForm employeeId={employeeId} />

        <section className="card">
          <div className="panel-title">
            <div>
              <h2>This year’s performance notes</h2>
              <p className="muted">Supervisor notes used as context for the annual review.</p>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Category</th>
                  <th>Area</th>
                  <th>Severity</th>
                  <th>Note</th>
                  <th>Logged by</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log: any) => (
                  <tr key={log.id}>
                    <td>{log.log_date}</td>
                    <td>{log.category}{Number(log.is_general || 0) ? " · General" : ""}</td>
                    <td>{log.area}</td>
                    <td>{log.severity}</td>
                    <td>
                      <strong>{log.note}</strong>
                      {log.private_note ? <><br /><span className="muted">Private: {log.private_note}</span></> : null}
                      {log.evidence_ref ? <><br /><span className="muted">Evidence: {log.evidence_ref}</span></> : null}
                    </td>
                    <td>{log.created_by || "—"}</td>
                  </tr>
                ))}
                {logs.length === 0 ? <tr><td colSpan={6}>No performance notes yet.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>

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
      </div>
    </Shell>
  );
}
