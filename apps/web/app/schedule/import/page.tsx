import Link from "next/link";
import { redirect } from "next/navigation";
import { AttendanceTemplateUploadClient } from "@/components/AttendanceTemplateUploadClient";
import { Shell } from "@/components/Shell";
import { currentSession } from "@/lib/session";

export default async function AttendanceTemplatePage() {
  const session = await currentSession();
  if (!session) redirect("/login");

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Attendance</span>
            <h1>Template upload</h1>
            <p className="muted">Download an employee grid CSV, fill in daily time-in/time-out rows, preview validation, then save to attendance.</p>
          </div>
          <div className="badge-row">
            <Link className="primary-link" href="/schedule">Back to schedule</Link>
          </div>
        </header>
        <AttendanceTemplateUploadClient />
      </div>
    </Shell>
  );
}
