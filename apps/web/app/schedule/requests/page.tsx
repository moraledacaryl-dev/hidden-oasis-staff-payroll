import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { ScheduleChangeReview } from "@/components/ScheduleChangeReview";
import { currentSession } from "@/lib/session";

export default async function ScheduleRequestsPage() {
  const session = await currentSession();
  if (!session) redirect("/login");
  if (!["owner", "payroll", "supervisor"].includes(session.role_key)) {
    return <Shell allowedRoles={["owner", "payroll", "supervisor"]}><div /></Shell>;
  }
  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div><span className="eyebrow">Schedule Control</span><h1>Shift-change requests</h1><p className="muted">Review staff requests, confirm coverage, update the official schedule, and print only when a formal copy is needed.</p></div>
        </header>
        <ScheduleChangeReview />
      </div>
    </Shell>
  );
}
