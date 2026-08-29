import { type NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, copySetCookies } from "@/lib/backend-proxy";

export async function GET(request: NextRequest) {
  const url = new URL(`${BACKEND_URL}/api/v1/healthcare/auth/login`);
  const returnTo = request.nextUrl.searchParams.get("return_to");
  if (returnTo) url.searchParams.set("return_to", returnTo);
  try {
    const upstream = await fetch(url, { redirect: "manual", cache: "no-store" });
    const location = upstream.headers.get("location");
    if (!location) return NextResponse.redirect(new URL("/auth/error", request.url), { status: 303 });
    const response = NextResponse.redirect(location, { status: 302 });
    copySetCookies(upstream, response);
    return response;
  } catch {
    return NextResponse.redirect(new URL("/auth/error", request.url), { status: 303 });
  }
}
