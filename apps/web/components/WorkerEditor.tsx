"use client";

import { useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppDrawer } from "./AppSurface";

export function WorkerEditor({ title, description, children, save, editing }: {
  title: string; description: string; children: ReactNode; editing: boolean;
  save: (data: FormData) => Promise<{ error: string; duplicateId?: number }>;
}) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<{ error: string; duplicateId?: number } | null>(null);
  const close = () => { if (!pending) router.push("/staff/manage", { scroll: false }); };
  return <AppDrawer open title={title} description={description} eyebrow="Worker record" onClose={close}
    footer={<div className="badge-row"><button type="button" className="button ghost" disabled={pending} onClick={close}>Cancel</button><button className="button" form="staff-record-form" disabled={pending}>{pending ? "Saving…" : editing ? "Save changes" : "Add worker"}</button></div>}>
    <form ref={formRef} id="staff-record-form" className="staff-drawer-form" aria-busy={pending} onSubmit={async (event) => {
      event.preventDefault(); setPending(true); setFailure(null);
      try {
        const result = await save(new FormData(event.currentTarget));
        setFailure(result);
        if (result.duplicateId) formRef.current?.querySelector<HTMLInputElement>('[name="employee_code"]')?.focus();
      } catch { setFailure({ error: "Unable to connect. Your entries are still here; please try again." }); }
      finally { setPending(false); }
    }}>
      {failure ? <div className="error-box" role="alert" id="worker-save-error">{failure.error} {failure.duplicateId ? <Link href={`/staff/manage?employee=${failure.duplicateId}`}>Open existing worker</Link> : null}</div> : null}
      {children}
    </form>
  </AppDrawer>;
}
