import { type NextRequest, NextResponse } from "next/server";
import { BACKEND_URL, upstreamFailure } from "@/lib/backend-proxy";

const METHODS_WITH_BODY = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function proxy(request: NextRequest, context: RouteContext<"/api/careflow/[...path]">) {
  const { path } = await context.params;
  if (path.some((segment) => segment === "." || segment === "..")) {
    return NextResponse.json({ detail: "Invalid API path." }, { status: 400 });
  }
  const target = new URL(`/api/v1/healthcare/${path.map(encodeURIComponent).join("/")}`, BACKEND_URL);
  target.search = request.nextUrl.search;
  const headers = new Headers({ Accept: request.headers.get("accept") ?? "application/json" });
  const cookie = request.headers.get("cookie");
  const contentType = request.headers.get("content-type");
  const csrf = request.cookies.get("careflow_csrf")?.value;
  const suppliedCsrf = request.headers.get("x-csrf-token");
  if (cookie) headers.set("Cookie", cookie);
  if (contentType) headers.set("Content-Type", contentType);
  if (METHODS_WITH_BODY.has(request.method)) {
    if (!csrf || !suppliedCsrf || csrf !== suppliedCsrf) {
      return NextResponse.json({ detail: "The CSRF token is missing or invalid." }, { status: 403 });
    }
    headers.set("x-csrf-token", suppliedCsrf);
  }

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: METHODS_WITH_BODY.has(request.method) ? await request.arrayBuffer() : undefined,
      cache: "no-store",
    });
    const responseHeaders = new Headers();
    for (const name of ["content-type", "content-disposition", "cache-control"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return upstreamFailure();
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
