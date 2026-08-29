import { type NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, copySetCookies } from "@/lib/backend-proxy";

export async function POST(request: NextRequest) {
  let response = NextResponse.redirect(new URL("/", request.url), { status: 303 });
  try {
    const csrf = request.cookies.get("careflow_csrf")?.value;
    const upstream = await fetch(`${BACKEND_URL}/api/v1/healthcare/auth/logout`, {
      method: "POST",
      cache: "no-store",
      headers: {
        Cookie: request.headers.get("cookie") ?? "",
        ...(csrf ? { "x-csrf-token": csrf } : {}),
      },
    });
    if (upstream.ok) {
      const body = (await upstream.json()) as { logout_url?: unknown };
      if (typeof body.logout_url === "string") {
        response = NextResponse.redirect(body.logout_url, { status: 303 });
      }
    }
    copySetCookies(upstream, response);
  } catch {
    // Clearing the local session still signs the browser out when Keycloak is unavailable.
  }
  response.cookies.delete("careflow_session");
  response.cookies.delete("careflow_csrf");
  return response;
}
