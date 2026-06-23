import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "https://compliance-ai-2xa8.onrender.com";

async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params;
    const target = new URL(`${BACKEND_URL}/api/v1/${path.join("/")}`);

    request.nextUrl.searchParams.forEach((value, key) => {
      target.searchParams.set(key, value);
    });

    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);

    const authorization = request.headers.get("authorization");
    if (authorization) headers.set("authorization", authorization);

    const body =
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : await request.arrayBuffer();

    const backendRes = await fetch(target.toString(), {
      method: request.method,
      headers,
      body,
    });

    const responseHeaders = new Headers();
    const responseContentType = backendRes.headers.get("content-type");
    if (responseContentType) {
      responseHeaders.set("content-type", responseContentType);
    }

    return new NextResponse(await backendRes.arrayBuffer(), {
      status: backendRes.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("API proxy error:", error);
    return NextResponse.json(
      { detail: "Unable to reach the backend API. Please try again shortly." },
      { status: 502 }
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
