import "server-only";

import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { serverRequest } from "@/lib/api/server";
import type { AuthUser } from "@/lib/api/types";

export async function currentUser(): Promise<AuthUser | null> {
  try {
    return await serverRequest<AuthUser>("/auth/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export async function requireRole(role: AuthUser["roles"][number], returnTo: string): Promise<AuthUser> {
  const user = await currentUser();
  if (!user) redirect(`/api/auth/login?return_to=${encodeURIComponent(returnTo)}`);
  if (!user.roles.includes(role)) redirect("/?access=denied");
  return user;
}
