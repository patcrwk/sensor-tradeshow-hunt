"use client";
import { api, ApiError } from "./api";

/** Ask, then delete a course. Returns true when it was deleted. */
export async function confirmDeleteCourse(c: { id: number; name: string; version: number }): Promise<boolean> {
  if (!confirm(`Delete the course "${c.name}" v${c.version}?\n\nThis removes the course and its survey files from the database. It cannot be undone. Printed QR signs keep working.`)) return false;
  try {
    await api(`/api/courses/${c.id}`, { method: "DELETE" });
    return true;
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      if (/active course/i.test(e.message)) { alert(e.message); return false; }
      if (!confirm(e.message)) return false;
      await api(`/api/courses/${c.id}?force=true`, { method: "DELETE" });
      return true;
    }
    alert(`Could not delete: ${(e as Error).message}`);
    return false;
  }
}
