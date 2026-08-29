import "server-only";

import { NextResponse } from "next/server";

export const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");

export function copySetCookies(upstream: Response, response: NextResponse): void {
  const headers = upstream.headers as Headers & { getSetCookie?: () => string[] };
  const values = headers.getSetCookie?.() ?? (headers.get("set-cookie") ? [headers.get("set-cookie")!] : []);
  for (const value of values) response.headers.append("set-cookie", value);
}

export function upstreamFailure(status = 502): NextResponse {
  return NextResponse.json({ detail: "The CareFlow service is unavailable." }, { status });
}
