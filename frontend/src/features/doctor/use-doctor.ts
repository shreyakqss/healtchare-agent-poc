import type { Department, RosterDoctor } from "@/lib/api";

export interface Me {
  id: string;
  name: string;
  username: string;
  department_id: string;
  department_name: string;
}

export function resolveMe(username: string | null, doctors: RosterDoctor[], departments: Department[]): Me | null {
  if (!username) return null;
  const doctor = doctors.find((entry) => entry.username?.toLocaleLowerCase() === username.toLocaleLowerCase());
  if (!doctor?.username) return null;
  const department = departments.find((entry) => entry.id === doctor.department_id);
  return {
    id: doctor.id,
    name: doctor.name,
    username: doctor.username,
    department_id: doctor.department_id,
    department_name: department?.name ?? doctor.department_id,
  };
}
