import { Suspense } from "react";
import { LoginForm } from "./LoginForm";
import { CalendarDays, Users, Check } from "lucide-react";

export default function LoginPage() {
  return (
    <main className="login-page">
      <section className="staff-login-identity" aria-label="Hidden Oasis Staff and Payroll">
        <div className="staff-login-wordmark"><span>HO</span> Hidden Oasis</div>
        <div className="staff-login-art" aria-hidden="true">
          <div className="staff-art-orbit" />
          <div className="staff-art-people"><Users size={36} strokeWidth={1.4} /><span>People</span><div className="staff-art-avatars"><i>AM</i><i>JL</i><i>MR</i></div></div>
          <div className="staff-art-schedule"><CalendarDays size={23} strokeWidth={1.6} /><span>Schedule</span><div className="staff-art-week">{["M", "T", "W", "T", "F", "S", "S"].map((day, i) => <span key={i} className={i < 5 ? "is-shift" : ""}>{day}</span>)}</div></div>
          <div className="staff-art-pay"><Check size={19} /><span>Payroll</span></div>
        </div>
        <div className="staff-login-caption"><h2>Staff &amp; Payroll</h2><p>Hidden Oasis</p></div>
      </section>
      <div className="staff-login-form-wrap">
      <Suspense fallback={<div className="card">Loading login...</div>}>
        <LoginForm />
      </Suspense>
      </div>
    </main>
  );
}
