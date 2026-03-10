export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("token");
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
