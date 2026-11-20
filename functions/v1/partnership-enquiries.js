const UPSTREAM =
  "https://trustng-api.onrender.com/v1/partnership-enquiries";

const MAX_BODY_BYTES = 16 * 1024;

function jsonResponse(status, detail, extraHeaders = {}) {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders,
    },
  });
}

export async function onRequest({ request }) {
  if (request.method !== "POST") {
    return jsonResponse(405, "Method not allowed. Use POST.", {
      Allow: "POST",
    });
  }

  const contentType = request.headers.get("content-type") || "";

  if (contentType.split(";")[0].trim().toLowerCase() !== "application/json") {
    return jsonResponse(415, "Content-Type must be application/json.");
  }

  const declaredLength = request.headers.get("content-length");

  if (declaredLength !== null) {
    if (!/^\d+$/.test(declaredLength)) {
      return jsonResponse(400, "Invalid Content-Length.");
    }

    if (Number(declaredLength) > MAX_BODY_BYTES) {
      return jsonResponse(413, "Request body is too large.");
    }
  }

  const reader = request.body?.getReader();
  const chunks = [];
  let totalBytes = 0;

  if (reader) {
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        totalBytes += value.byteLength;

        if (totalBytes > MAX_BODY_BYTES) {
          await reader.cancel();
          return jsonResponse(413, "Request body is too large.");
        }

        chunks.push(value);
      }
    } catch {
      return jsonResponse(400, "Could not read request body.");
    }
  }

  const body = new Uint8Array(totalBytes);
  let offset = 0;

  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    const upstream = await fetch(UPSTREAM, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
      },
      body,
      redirect: "manual",
    });

    if (upstream.status >= 300 && upstream.status < 400) {
      return jsonResponse(
        502,
        "The enquiry service returned an unexpected redirect.",
      );
    }

    const headers = new Headers();
    headers.set(
      "Content-Type",
      upstream.headers.get("content-type") ||
        "application/json; charset=utf-8",
    );
    headers.set("Cache-Control", "no-store");

    const responseBody =
      upstream.status === 204 ||
      upstream.status === 205 ||
      upstream.status === 304
        ? null
        : upstream.body;

    return new Response(responseBody, {
      status: upstream.status,
      headers,
    });
  } catch (error) {
    console.error(
      "Partnership proxy failed:",
      error instanceof Error ? error.message : String(error),
    );
    return jsonResponse(
      502,
      "The enquiry service is temporarily unavailable. Please try again.",
    );
  }
}
