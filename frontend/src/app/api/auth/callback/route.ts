import { type NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, copySetCookies } from "@/lib/backend-proxy";

export async function GET(request: NextRequest) {
  const url = new URL(`${BACKEND_URL}/api/v1/healthcare/auth/callback${request.nextUrl.search}`);
  try {
    const upstream = await fetch(url, {
      cache: "no-store",
      redirect: "manual",
      headers: { Cookie: request.headers.get("cookie") ?? "" },
    });
    const location = upstream.headers.get("location");
    if (!location || !location.startsWith("/") || location.startsWith("//") || location.includes("\\")) {
      return NextResponse.redirect(new URL("/auth/error", request.url), { status: 303 });
    }
    const response = NextResponse.redirect(new URL(location, request.url), { status: 303 });
    copySetCookies(upstream, response);
    return response;
  } catch {
    return NextResponse.redirect(new URL("/auth/error", request.url), { status: 303 });
  }
}
