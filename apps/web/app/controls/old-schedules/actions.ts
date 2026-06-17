"use server";

import { redirect } from "next/navigation";

export async function submitOldSchedules() {
  redirect("/controls/old-schedules?ok=1");
}
