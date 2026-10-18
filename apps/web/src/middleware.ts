import { NextResponse } from "next/server";

/** Pass-through — site is live (rebuild / maintenance gate removed). */
export function middleware() {
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
