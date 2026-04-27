import { NextRequest, NextResponse } from "next/server";

export function middleware(req: NextRequest) {
  const start = Date.now();
  const res = NextResponse.next();
  // App Router middleware can't observe response status easily; log on entry.
  // Format: ISO_TIME | METHOD | PATH | client_ip | user-agent
  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
    req.headers.get("x-real-ip") ??
    "-";
  const ua = req.headers.get("user-agent") ?? "-";
  console.log(
    `${new Date().toISOString()} | ${req.method} ${req.nextUrl.pathname}${req.nextUrl.search} | ip=${ip} | ua="${ua}" | t+${Date.now() - start}ms`
  );
  return res;
}

export const config = {
  // Skip Next.js internals and static assets
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
