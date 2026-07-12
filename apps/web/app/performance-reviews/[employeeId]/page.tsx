import Link from "next/link";
import { redirect } from "next/navigation";
import { AnnualReviewForm } from "@/components/AnnualReviewForm";
import { PerformanceLogForm } from "@/components/PerformanceLogForm";
import { Shell } from "@/components/Shell";
import { PageHeading, SectionBody, SectionCard, SectionHeader } from "@/components/UiPrimitives";
import { apiBaseUrl, backendHeaders } from "@/lib/api";
import { currentSession } from "@/lib/session";
import type { AnnualReviewItem, PerformanceLog } from "@/lib/performance-types";

type ReviewResponse = { ok: boolean; items: AnnualReviewItem[] };
type LogsResponse = { ok: boolean; items: PerformanceLog[] };

async function loadAnnualReviews(year: number): Promise<ReviewResponse> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/performance/annual-reviews?year=${year}`, { headers: await backendHeaders(), cache: "no-store" });
  if (!response.ok) return { ok: false, items: [] };
  return response.json() as Promise<ReviewResponse>;
}

async function loadLogs(employeeId: number, year: number): Promise<LogsResponse> {
  const response = await fetch(`${apiBaseUrl()}/api/v1/performance/logs?employee_id=${employeeId}&year=${year}`, { headers: await backendHeaders(), cache: "no-store" });
  if (!response.ok) return { ok: false, items: [] };
  return response.json() as Promise<LogsResponse>;
}

export default async function EmployeePerformancePage({ params, searchParams }: { params: Promise<{ employeeId: string }>; searchParams: Promise<{ year?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;

  const resolvedParams = await params;
  const resolvedSearch = await searchParams;
  const employeeId = Number(resolvedParams.employeeId);
  const year = Number(resolvedSearch.year || new Date().getFullYear());
  const [reviewsData, logsData] = await Promise.all([loadAnnualReviews(year), loadLogs(employeeId, year)]);
  const item = (reviewsData.items || []).find((row) => Number(row.employee?.id) === employeeId);

  if (!item) return <Shell allowedRoles={["owner", "supervisor"]}><div className="page review-page"><Link className="button secondary" href={`/performance-reviews?year=${year}`}>Back to reviews</Link><SectionCard><SectionBody>Employee not found.</SectionBody></SectionCard></div></Shell>;

  const employee = item.employee;
  const logs = logsData.items || [];
  const currentMonth = new Date().toISOString().slice(0, 7);
  const positive = logs.filter((log) => log.category === "Positive").length;
  const concerns = logs.filter((log) => log.category === "Concern").length;
  const currentStatus = item.review?.status || "Not started";

  return (
    <Shell allowedRoles={["owner", "supervisor"]}>
      <div className="page people-page review-page">
        <PageHeading eyebrow="Performance" title={employee.full_name} description={`${year} review workspace with current notes, review history, and attendance context.`} actions={<><Link className="button secondary" href={`/performance-reviews?year=${year}`}>Back to reviews</Link><Link className="button" href={`/attendance?month=${currentMonth}&employee=${encodeURIComponent(employee.full_name || "")}`}>View attendance</Link></>} />

        <section className="performance-context">
          <div><span>Employee code</span><strong>{employee.employee_code || "—"}</strong></div>
          <div><span>Department</span><strong>{employee.department || "—"}</strong></div>
          <div><span>Position</span><strong>{employee.position || "—"}</strong></div>
          <div><span>Review stage</span><strong>{currentStatus}</strong></div>
        </section>

        <section className="people-kpis">
          <div className="people-kpi"><span>Performance notes</span><strong>{logs.length}</strong></div>
          <div className="people-kpi"><span>Positive notes</span><strong>{positive}</strong></div>
          <div className="people-kpi"><span>Concerns</span><strong>{concerns}</strong></div>
          <div className="people-kpi"><span>Overall rating</span><strong>{item.review?.overall_rating ? `${item.review.overall_rating}/5` : "—"}</strong></div>
        </section>

        <section className="review-two-col">
          <div className="review-side">
            <PerformanceLogForm employeeId={employeeId} />
            <SectionCard>
              <SectionHeader title="This year’s performance notes" description={`${logs.length} recorded observation${logs.length === 1 ? "" : "s"}.`} />
              <SectionBody><div className="review-log-list">{logs.map((log) => <article key={log.id} className="review-log-card"><div className="review-log-meta"><span className="badge">{log.log_date}</span><span className={log.category === "Concern" ? "badge warning" : log.category === "Positive" ? "badge ok" : "badge"}>{log.category}{Number(log.is_general || 0) ? " · General" : ""}</span><span className="badge">{log.area}</span><span className={log.severity === "High" ? "badge danger" : log.severity === "Medium" ? "badge warning" : "badge"}>{log.severity}</span></div><div className="review-log-note"><strong>{log.note}</strong></div>{log.private_note ? <span className="muted">Private: {log.private_note}</span> : null}{log.evidence_ref ? <span className="muted">Evidence: {log.evidence_ref}</span> : null}<span className="muted">Logged by {log.created_by || "—"}</span></article>)}{logs.length === 0 ? <p className="footer-note">No performance notes yet.</p> : null}</div></SectionBody>
            </SectionCard>
          </div>

          <SectionCard>
            <SectionHeader title="Annual review" description="Draft, submit, and finalize the formal review while preserving previous review context." />
            <SectionBody><AnnualReviewForm employee={employee} review={item.review} previousReviews={item.previous_reviews || []} reviewYear={year} canFinalize={session.role_key === "owner"} /></SectionBody>
          </SectionCard>
        </section>
      </div>
    </Shell>
  );
}
