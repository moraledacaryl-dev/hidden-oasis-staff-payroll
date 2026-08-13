import { NextRequest, NextResponse } from "next/server";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function requestHost(request: NextRequest): string {
  return (
    request.headers.get("x-forwarded-host") ||
    request.headers.get("host") ||
    ""
  )
    .split(",")[0]
    .trim()
    .toLowerCase();
}

function originHost(origin: string): string | null {
  try {
    return new URL(origin).host.toLowerCase();
  } catch {
    return null;
  }
}

export function middleware(request: NextRequest) {
  if (SAFE_METHODS.has(request.method.toUpperCase())) {
    return NextResponse.next();
  }

  const fetchSite = request.headers
    .get("sec-fetch-site")
    ?.trim()
    .toLowerCase();

  if (fetchSite === "cross-site") {
    return NextResponse.json(
      {
        ok: false,
        message: "Cross-site mutation request rejected.",
      },
      { status: 403 },
    );
  }

  const origin = request.headers.get("origin");

  // Non-browser/internal requests may legitimately omit Origin.
  if (!origin) {
    return NextResponse.next();
  }

  const expectedHost = requestHost(request);
  const suppliedHost = originHost(origin);

  if (
    !expectedHost ||
    !suppliedHost ||
    suppliedHost !== expectedHost
  ) {
    return NextResponse.json(
      {
        ok: false,
        message: "Request origin is not allowed.",
      },
      { status: 403 },
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/api/:path*"],
};
