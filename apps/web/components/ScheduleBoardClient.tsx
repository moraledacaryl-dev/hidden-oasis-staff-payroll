"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { moveScheduledShift } from "@/app/schedule/actions";
import { ScheduleDayEditorModal } from "@/components/ScheduleDayEditorModal";
import styles from "@/app/schedule/page.module.css";

type Shift = {
  id: number;
  employee_id: number | null;
  shift_date: string;
  start_time: string;
  end_time: string;
  position: string;
  department?: string | null;
  employee_department?: string | null;
  break_minutes: number;
  status: string;
  notes?: string | null;
  employee_name?: string | null;
  planned_paid_hours: number;
  is_overnight: boolean;
  source?: string;
  movable?: boolean;
};

type ScheduleEmployee = { id: number; full_name: string; employee_code?: string; department?: string; position?: string };

type Props = {
  days: string[];
  shifts: Shift[];
  employees: ScheduleEmployee[];
  canEdit: boolean;
};

function numberText(value: number | null | undefined, digits = 2): string {
  return Number(value || 0).toLocaleString("en-PH", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function dayLabel(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-PH", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function ScheduleBoardClient({ days, shifts, employees, canEdit }: Props) {
  const router = useRouter();
  const [dragId, setDragId] = useState<number | null>(null);
  const [overDay, setOverDay] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [editor, setEditor] = useState<{ day: string; shift: Shift | null } | null>(null);
  const [isPending, startTransition] = useTransition();

  const byDay = useMemo(() => {
    return days.reduce<Record<string, Shift[]>>((acc, day) => {
      acc[day] = shifts.filter((item) => item.shift_date === day);
      return acc;
    }, {});
  }, [days, shifts]);

  function onDrop(day: string) {
    if (!canEdit || !dragId) return;
    const source = shifts.find((item) => item.id === dragId);
    setOverDay(null);
    setDragId(null);
    if (!source || source.shift_date === day) return;

    startTransition(async () => {
      const result = await moveScheduledShift(source.id, day);
      if (!result?.ok) {
        setMessage(result?.message || "Could not move shift.");
        return;
      }
      setMessage("Shift moved.");
      router.refresh();
    });
  }

  return (
    <>
      <div className={styles.boardHint}>{isPending ? "Saving…" : message || (canEdit ? "Click a card or empty day to edit. Drag planned shifts to move days." : "Supervisor view is read-only.")}</div>
      <div className={styles.scheduleGrid}>
        {days.map((day) => {
          const dayShifts = byDay[day] || [];
          const dayHours = dayShifts.reduce((sum, item) => sum + Number(item.planned_paid_hours || 0), 0);
          const isOver = overDay === day;

          return (
            <div
              className={`${styles.scheduleDay} ${isOver ? styles.dropTarget : ""}`}
              key={day}
              onDragOver={(event) => {
                if (!canEdit) return;
                event.preventDefault();
                setOverDay(day);
              }}
              onDragLeave={() => setOverDay(null)}
              onDrop={() => onDrop(day)}
            >
              <div className={styles.scheduleDayHead}>
                <div>
                  <strong>{dayLabel(day)}</strong>
                  <span>{numberText(dayHours)} hrs</span>
                </div>
                <span>{dayShifts.length} shift{dayShifts.length === 1 ? "" : "s"}</span>
              </div>

              <div className={styles.scheduleStack}>
                {dayShifts.map((shift) => (
                  <button
                    type="button"
                    className={`${styles.shiftCard} ${dragId === shift.id ? styles.dragging : ""}`}
                    draggable={canEdit && shift.id > 0 && shift.movable !== false}
                    key={shift.id}
                    onClick={() => setEditor({ day, shift })}
                    onDragStart={() => {
                      if (!canEdit || shift.id < 0 || shift.movable === false) return;
                      setDragId(shift.id);
                    }}
                    onDragEnd={() => {
                      setDragId(null);
                      setOverDay(null);
                    }}
                  >
                    <div className={styles.shiftTop}>
                      <strong>{shift.employee_name || "Unassigned"}</strong>
                      <span>{shift.position}</span>
                    </div>
                    <span>{shift.start_time}–{shift.end_time}{shift.is_overnight ? " +1" : ""}</span>
                    <span>{numberText(shift.planned_paid_hours)} paid hrs · break {shift.break_minutes}m</span>
                    <span>{shift.employee_department || shift.department || "No department"}</span>
                    {shift.source === "imported" ? <span className={styles.legacyNote}>Legacy imported row</span> : null}
                    {shift.notes ? <p className="muted">{shift.notes}</p> : null}
                  </button>
                ))}
                {dayShifts.length === 0 ? (
                  <button className={styles.emptyDay} type="button" onClick={() => canEdit && setEditor({ day, shift: null })}>
                    {canEdit ? "Click to add or edit day" : "No shifts"}
                  </button>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
      <ScheduleDayEditorModal
        open={Boolean(editor)}
        day={editor?.day || days[0]}
        shift={editor?.shift || null}
        employees={employees}
        canEdit={canEdit}
        onClose={() => setEditor(null)}
      />
    </>
  );
}
