import { proxyDocumentation } from "../_shared/proxy.js";

export async function onRequest({ request }) {
  return proxyDocumentation(request, "/docs/oauth2-redirect");
}
