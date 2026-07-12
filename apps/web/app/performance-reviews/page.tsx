import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { StatusBadge } from "@/components/StatusBadge";
import { Notice, PageHeading, SectionBody, SectionCard, SectionHeader, Toolbar } from "@/components/UiPrimitives";
import { apiBaseUrl, backendHeaders } from "@/lib/api";
import { currentSession } from "@/lib/session";
import type { AnnualReviewItem } from "@/lib/performance-types";

type AnnualReviewResponse = { ok: boolean; year: number; items: AnnualReviewItem[]; error?: string };
function defaultYear() { return new Date().getFullYear(); }
async function loadAnnualReviews(year: number): Promise<AnnualReviewResponse> { const response = await fetch(`${apiBaseUrl()}/api/v1/performance/annual-reviews?year=${year}`, { headers: await backendHeaders(), cache: "no-store" }); if (!response.ok) { const text = await response.text().catch(() => ""); return { ok: false, year, items: [], error: `Annual review API failed ${response.status}: ${text}` }; } return response.json() as Promise<AnnualReviewResponse>; }

export default async function PerformanceReviewsPage({ searchParams }: { searchParams: Promise<{ year?: string; employee?: string }> }) {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "supervisor"].includes(session.role_key)) return <Shell allowedRoles={["owner", "supervisor"]}><div /></Shell>;
  const params = await searchParams;
  const year = Number(params.year || defaultYear());
  const employeeFilter = (params.employee || "").trim().toLowerCase();
  const data = await loadAnnualReviews(year);
  const items = (data.items || []).filter((item) => !employeeFilter || String(item.employee?.full_name || "").toLowerCase().includes(employeeFilter));
  const notStarted = items.filter((item) => !item.review).length;
  const draftCount = items.filter((item) => item.review?.status === "Draft").length;
  const submittedCount = items.filter((item) => item.review?.status === "Submitted").length;
  const finalizedCount = items.filter((item) => item.review?.status === "Finalized").length;

  return <Shell allowedRoles={["owner", "supervisor"]}><div className="page people-page review-page">
    <PageHeading eyebrow="People" title={`Performance reviews ${year}`} description="Track annual review progress, private drafts, submitted reviews, and finalized employee records." actions={<Link className="button secondary" href="/staff">Staff directory</Link>} />
    <section className="review-cycle"><div className="review-kpi"><strong>{notStarted}</strong><span>Not started</span></div><div className="review-kpi"><strong>{draftCount}</strong><span>Private drafts</span></div><div className="review-kpi"><strong>{submittedCount}</strong><span>Submitted</span></div><div className="review-kpi"><strong>{finalizedCount}</strong><span>Finalized</span></div></section>
    <SectionCard><Toolbar><form className="people-filter" action="/performance-reviews"><label>Staff search<input name="employee" placeholder="Search employee name" defaultValue={params.employee || ""} /></label><label>Review year<input name="year" type="number" min="2024" max="2100" defaultValue={year} /></label><button className="button" type="submit">Apply</button></form><StatusBadge label={`${items.length} employees`} /></Toolbar></SectionCard>
    {!data.ok ? <Notice tone="danger"><strong>Annual reviews did not load.</strong><br />{data.error || "The review API returned an error."}</Notice> : null}
    <SectionCard><SectionHeader title="Review cycle" description="Open a worker to continue the annual review and inspect previous comments." /><SectionBody flush><div className="people-table-wrap"><table className="people-table"><thead><tr><th>Employee</th><th>Department</th><th>Position</th><th>Stage</th><th>Overall</th><th>Previous review</th><th /></tr></thead><tbody>{items.map((item) => { const previous = (item.previous_reviews || [])[0]; const status = item.review?.status || "Not started"; return <tr key={item.employee.id}><td><strong>{item.employee.full_name}</strong><br /><span className="muted">{item.employee.employee_code || "—"}</span></td><td>{item.employee.department || "—"}</td><td>{item.employee.position || "—"}</td><td><StatusBadge label={status} tone={status === "Finalized" ? "ok" : status === "Submitted" ? "warning" : "neutral"} /></td><td>{item.review?.overall_rating ? `${item.review.overall_rating}/5` : "—"}</td><td>{previous ? `${previous.review_year}: ${previous.strengths || previous.improvements || previous.supervisor_recommendation || "No comment"}` : "No previous comments"}</td><td><Link className="button small ghost" href={`/performance-reviews/${item.employee.id}?year=${year}`}>Open review</Link></td></tr>; })}{!items.length ? <tr><td colSpan={7}>No employees found.</td></tr> : null}</tbody></table></div></SectionBody></SectionCard>
  </div></Shell>;
}
