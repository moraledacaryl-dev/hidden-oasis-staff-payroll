import { redirect } from "next/navigation";
import { AttendanceTemplateUploadClient } from "@/components/AttendanceTemplateUploadClient";
import { Shell } from "@/components/Shell";
import { currentSession } from "@/lib/session";

export default async function AttendanceTemplatePage() {
  const session = await currentSession();
  if (!session) redirect("/login");

  return (
    <Shell allowedRoles={["owner"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Attendance</span>
            <h1>Template upload</h1>
          </div>
        </header>
        <AttendanceTemplateUploadClient />
      </div>
    </Shell>
  );
}
