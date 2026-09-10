export async function clientRequest(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try { return await fetch(input, init); }
  catch { return new Response(JSON.stringify({ ok: false, detail: "Unable to connect. Please check your connection and try again.", message: "Unable to connect. Please try again." }), { status: 503, headers: { "Content-Type": "application/json" } }); }
}
