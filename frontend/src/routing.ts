export function customerQrTokenFromPath(pathname: string): string | null {
  const match = /^\/qr\/([^/]+)\/?$/.exec(pathname);
  if (!match) return null;

  try {
    const token = decodeURIComponent(match[1]);
    if (!token || token.includes("/") || token.length > 128) return null;
    return token;
  } catch {
    return null;
  }
}
