export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  if (!localStorage.getItem("token")) return false;
  return !isTokenExpired();
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function getEmail(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("email");
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("token");
  localStorage.removeItem("email");
}

export function setToken(token: string): void {
  localStorage.setItem("token", token);
}

export function setAuth(token: string, email: string): void {
  localStorage.setItem("token", token);
  localStorage.setItem("email", email);
}

/** Decode a JWT payload (base64url). No signature verification — this is only
 * a client-side hint for proactive expiry handling; the server remains the
 * source of truth and still returns 401 on a bad/expired token. */
function decodeJwtPayload(token: string): { exp?: number } | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const b64 = part.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(b64));
  } catch {
    return null;
  }
}

/** Unix-seconds `exp` of the stored token, or null if absent/unparseable. */
export function getTokenExp(): number | null {
  const token = getToken();
  if (!token) return null;
  const payload = decodeJwtPayload(token);
  return typeof payload?.exp === "number" ? payload.exp : null;
}

/** True when a token is present and its `exp` is in the past. A token with no
 * `exp` claim is treated as not-expired (the server will still reject it). */
export function isTokenExpired(): boolean {
  const exp = getTokenExp();
  if (exp == null) return false;
  return Date.now() >= exp * 1000;
}
