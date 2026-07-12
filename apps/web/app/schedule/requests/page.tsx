import Link from "next/link";
import { redirect } from "next/navigation";
import { Shell } from "@/components/Shell";
import { ScheduleChangeReview } from "@/components/ScheduleChangeReview";
import { PageHeading } from "@/components/UiPrimitives";
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
        <PageHeading
          eyebrow="Schedule control"
          title="Shift-change requests"
          description="Review swaps, date or time changes, coverage confirmation, and employee communication in one operational queue."
          actions={<div className="operations-tabs"><Link href="/schedule">Weekly schedule</Link><Link href="/schedule/requests" aria-current="page">Shift requests</Link><Link href="/schedule/import">Attendance upload</Link></div>}
        />
        <ScheduleChangeReview />
      </div>
    </Shell>
  );
}
