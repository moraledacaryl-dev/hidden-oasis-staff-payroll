import { Shell } from "@/components/Shell";
import { PasswordChangeForm } from "@/components/PasswordChangeForm";

export default async function PasswordSettingsPage() {
  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor", "staff"]}>
      <div className="page">
        <header className="page-header">
          <div className="grid">
            <span className="eyebrow">Password</span>
            <h1>Change password</h1>
            <p className="muted">Update your own sign-in password. Current password is required.</p>
          </div>
        </header>
        <section className="card">
          <PasswordChangeForm />
        </section>
      </div>
    </Shell>
  );
}
