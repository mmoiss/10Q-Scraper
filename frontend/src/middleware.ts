import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // Only protect /app routes
    if (pathname.startsWith("/app")) {
        const sessionToken = request.cookies.get("session_token");

        console.log("[Middleware] Checking auth for:", pathname);
        console.log("[Middleware] Session token present:", !!sessionToken?.value);

        // No cookie at all - redirect to login
        if (!sessionToken?.value) {
            console.log("[Middleware] No token, redirecting to login");
            return NextResponse.redirect(new URL("/", request.url));
        }

        // Verify session with backend
        try {
            const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
            console.log("[Middleware] Checking with backend:", backendUrl);

            const response = await fetch(`${backendUrl}/api/auth/check`, {
                method: "GET",
                headers: {
                    "Cookie": `session_token=${sessionToken.value}`,
                },
                cache: "no-store",
            });

            console.log("[Middleware] Backend response status:", response.status);

            if (response.ok) {
                const data = await response.json();
                console.log("[Middleware] Auth response:", data);

                if (data.authenticated === true) {
                    // Valid session, allow access
                    return NextResponse.next();
                }
            }

            // Invalid session - clear cookie and redirect
            console.log("[Middleware] Invalid session, redirecting");
            const redirectResponse = NextResponse.redirect(new URL("/", request.url));
            redirectResponse.cookies.delete("session_token");
            return redirectResponse;

        } catch (error) {
            console.error("[Middleware] Error:", error);
            const redirectResponse = NextResponse.redirect(new URL("/", request.url));
            redirectResponse.cookies.delete("session_token");
            return redirectResponse;
        }
    }

    return NextResponse.next();
}

export const config = {
    matcher: ["/app/:path*"],
};
