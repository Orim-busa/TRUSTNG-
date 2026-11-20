const API_ORIGIN = "https://trustng-api.onrender.com";

export async function proxyDocumentation(request, path) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method not allowed.", {
      status: 405,
      headers: {
        "Allow": "GET, HEAD",
        "Cache-Control": "no-store",
      },
    });
  }

  try {
    const upstreamUrl = new URL(`${API_ORIGIN}${path}`);
    upstreamUrl.search = new URL(request.url).search;

    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers: {
        "Accept": request.headers.get("Accept") || "*/*",
      },
      redirect: "manual",
    });

    if (upstream.status >= 300 && upstream.status < 400) {
      return new Response(
        JSON.stringify({
          detail: "The documentation service returned an unexpected redirect.",
        }),
        {
          status: 502,
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
          },
        },
      );
    }

    const headers = new Headers(upstream.headers);
    headers.set("Cache-Control", "no-store");
    headers.delete("Set-Cookie");

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers,
    });
  } catch (error) {
    console.error(
      "TrustNG documentation proxy failed:",
      error instanceof Error ? error.message : String(error),
    );
    return new Response(
      JSON.stringify({
        detail: "TrustNG API documentation is temporarily unavailable.",
      }),
      {
        status: 502,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-store",
        },
      },
    );
  }
}
