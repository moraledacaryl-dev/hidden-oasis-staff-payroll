import Link from "next/link";
import { redirect } from "next/navigation";
import { AttendanceTemplateUploadClient } from "@/components/AttendanceTemplateUploadClient";
import { Shell } from "@/components/Shell";
import { PageHeading } from "@/components/UiPrimitives";
import { currentSession } from "@/lib/session";

export default async function AttendanceTemplatePage() {
  const session = await currentSession();
  if (!session) redirect("/login");

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page attendance-import-page">
        <PageHeading
          eyebrow="Attendance"
          title="Attendance upload"
          description="Download the employee grid, validate completed attendance rows, then commit only clean data to the review workflow."
          actions={<div className="operations-tabs"><Link href="/schedule">Weekly schedule</Link><Link href="/schedule/requests">Shift requests</Link><Link href="/schedule/import" aria-current="page">Attendance upload</Link></div>}
        />
        <AttendanceTemplateUploadClient />
      </div>
    </Shell>
  );
}
