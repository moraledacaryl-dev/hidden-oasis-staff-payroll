import { Shell } from "@/components/Shell";
import { MfaSettingsForm } from "@/components/MfaSettingsForm";
import { currentSession } from "@/lib/session";

export default async function SecuritySettingsPage() {
  const session = await currentSession();
  const privilegedRole = session?.role_key === "owner" || session?.role_key === "payroll";
  const privilegedMfaRequired =
    privilegedRole &&
    process.env.STAFF_PAYROLL_REQUIRE_PRIVILEGED_MFA?.trim().toLowerCase() === "true";

  return (
    <Shell allowedRoles={["owner", "payroll", "supervisor", "staff"]} allowAccountSetup>
      <div className="page">
        <header className="page-header">
          <div>
            <span className="eyebrow">Account</span>
            <h1>Authenticator</h1>
          </div>
        </header>
        <section className="card content-narrow">
          <MfaSettingsForm
            enabled={Boolean(session?.mfa_enabled)}
            privilegedMfaRequired={Boolean(privilegedMfaRequired)}
          />
        </section>
      </div>
    </Shell>
  );
}
