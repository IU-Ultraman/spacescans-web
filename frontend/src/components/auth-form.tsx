"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { setAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface AuthFormProps {
  mode: "login" | "signup";
}

type View = "login" | "signup" | "change";

export function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  // The change-password view lives on the /login route (a toggle, not a new
  // route) so a wrong-current-password 401 shows inline instead of tripping the
  // global "redirect to /login on 401" handler.
  const [view, setView] = useState<View>(mode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const isSignup = view === "signup";
  const isChange = view === "change";

  function goto(next: View) {
    setView(next);
    setError("");
    setNewPassword("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      let data: { access_token: string };

      if (isSignup) {
        data = await api.signup({
          email,
          password,
          first_name: firstName,
          last_name: lastName,
        });
      } else if (isChange) {
        data = await api.changePassword({
          email,
          current_password: password,
          new_password: newPassword,
        });
      } else {
        data = await api.login({ email, password });
      }

      setAuth(data.access_token, email);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  const title = isSignup
    ? "Create your account"
    : isChange
      ? "Change your password"
      : "Sign in to your account";
  const description = isSignup
    ? "Fill in your details to get started"
    : isChange
      ? "Verify with your current password, then set a new one"
      : "Enter your credentials to continue";
  const submitLabel = loading
    ? isSignup
      ? "Creating account..."
      : isChange
        ? "Updating..."
        : "Signing in..."
    : isSignup
      ? "Create account"
      : isChange
        ? "Change password"
        : "Sign in";

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <Link
            href="/"
            className="inline-block text-3xl font-bold tracking-tight text-foreground transition-colors hover:text-primary"
          >
            SPACESCANS
          </Link>
          <p className="mt-1 text-sm text-muted-foreground">
            Spatial Scanning Analysis Platform
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-xl">{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {isSignup && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label htmlFor="firstName">First name</Label>
                    <Input
                      id="firstName"
                      type="text"
                      placeholder="Jane"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      required
                      disabled={loading}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="lastName">Last name</Label>
                    <Input
                      id="lastName"
                      type="text"
                      placeholder="Doe"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      required
                      disabled={loading}
                    />
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={loading}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">
                  {isChange ? "Current password" : "Password"}
                </Label>
                <Input
                  id="password"
                  type="password"
                  placeholder={
                    isChange
                      ? "Enter your current password"
                      : "Enter your password"
                  }
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                />
              </div>

              {isChange && (
                <div className="space-y-2">
                  <Label htmlFor="newPassword">New password</Label>
                  <Input
                    id="newPassword"
                    type="password"
                    placeholder="Enter a new password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    disabled={loading}
                  />
                </div>
              )}

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button
                type="submit"
                className="w-full"
                size="lg"
                disabled={loading}
              >
                {submitLabel}
              </Button>
            </form>

            <div className="mt-4 space-y-1 text-center text-sm text-muted-foreground">
              {isSignup && (
                <p>
                  Already have an account?{" "}
                  <Link
                    href="/login"
                    className="font-medium text-primary underline-offset-4 hover:underline"
                  >
                    Sign in
                  </Link>
                </p>
              )}
              {view === "login" && (
                <>
                  <p>
                    Don&apos;t have an account?{" "}
                    <Link
                      href="/signup"
                      className="font-medium text-primary underline-offset-4 hover:underline"
                    >
                      Sign up
                    </Link>
                  </p>
                  <p>
                    <button
                      type="button"
                      onClick={() => goto("change")}
                      className="font-medium text-primary underline-offset-4 hover:underline"
                    >
                      Change password
                    </button>
                  </p>
                </>
              )}
              {isChange && (
                <p>
                  <button
                    type="button"
                    onClick={() => goto("login")}
                    className="font-medium text-primary underline-offset-4 hover:underline"
                  >
                    ← Back to sign in
                  </button>
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
