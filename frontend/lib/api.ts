const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "https://compliance-ai-2xa8.onrender.com";

// Browser requests go through the Next.js rewrite (same origin, no CORS).
export const API_BASE = "/api/proxy";

// Direct backend URL — only for non-fetch navigation if needed.
export const BACKEND_API_URL = `${BACKEND_URL}/api/v1`;
