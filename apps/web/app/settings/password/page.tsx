import { Shell } from "@/components/Shell";
import { PasswordChangeForm } from "@/components/PasswordChangeForm";

export default async function PasswordSettingsPage() {
  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor", "staff"]} allowAccountSetup>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Password</span>
            <h1>Change password</h1>
          </div>
        </header>
        <section className="card">
          <PasswordChangeForm />
        </section>
      </div>
    </Shell>
  );
}
