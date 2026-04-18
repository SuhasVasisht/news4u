export async function parseJsonBody(request: Request) {
  try {
    const text = await request.text();
    if (!text.trim()) {
      return null;
    }

    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}
