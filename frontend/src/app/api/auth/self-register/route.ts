import { type NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, copySetCookies } from "@/lib/backend-proxy";

export async function POST(request: NextRequest) {
  const url = new URL(`${BACKEND_URL}/api/v1/healthcare/auth/self-register`);
  url.searchParams.set("return_to", "/patient");
  const upstream = await fetch(url, { method: "POST", cache: "no-store" });
  if (!upstream.ok) {
    return NextResponse.json({ error: "Could not create the account." }, { status: upstream.status });
  }
  const body = await upstream.json();
  const response = NextResponse.json(body);
  copySetCookies(upstream, response);
  return response;
}
