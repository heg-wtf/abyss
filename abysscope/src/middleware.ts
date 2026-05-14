import { NextResponse, type NextRequest } from "next/server";

/**
 * Redirect mobile user agents to the ``/mobile`` route tree.
 *
 * When a phone user types just the dashboard URL (or scans a QR code
 * shared from desktop) they land on the heavyweight desktop dashboard
 * heatmap with a sidebar that does not fit a phone screen. We sniff
 * the User-Agent on the root path only and bounce them to
 * ``/mobile``. The desktop UI stays one tap away via the
 * "Desktop UI" link in the mobile header.
 *
 * The matcher restricts the middleware to a tiny set of paths so we
 * do not run UA parsing on every API call. Anything already under
 * ``/mobile`` or ``/api`` is exempt by config below.
 */

const MOBILE_UA = /Mobi|Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i;

export function middleware(request: NextRequest) {
  const { nextUrl } = request;

  // Opt-out via ``?desktop=1`` so a curious user can still inspect the
  // dashboard from their phone.
  if (nextUrl.searchParams.get("desktop") === "1") {
    return NextResponse.next();
  }

  const ua = request.headers.get("user-agent") || "";
  if (!MOBILE_UA.test(ua)) {
    return NextResponse.next();
  }

  const target = nextUrl.clone();
  target.pathname = "/mobile";
  target.search = "";
  return NextResponse.redirect(target);
}

export const config = {
  // Only intercept the root path; mobile users navigating elsewhere
  // (e.g. into a specific dashboard page from a share link) are not
  // redirected.
  matcher: ["/"],
};
