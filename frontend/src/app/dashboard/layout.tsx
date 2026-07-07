"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { clearToken, getEmail, isAuthenticated } from "@/lib/auth";
import { ThemeToggle } from "@/components/theme-toggle";
import { LogOut } from "lucide-react";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    setEmail(getEmail());
    setChecked(true);

    // #5: proactively boot the user when the JWT expires mid-session, so they
    // don't fill out a form only to be rejected on submit. isAuthenticated()
    // now also checks the token's exp; re-check on an interval to catch expiry
    // while the user idles on a page.
    const interval = setInterval(() => {
      if (!isAuthenticated()) {
        clearToken();
        router.replace("/login");
      }
    }, 30000);
    return () => clearInterval(interval);
  }, [router]);

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  // Don't render anything until auth check completes
  if (!checked) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Top navigation bar */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-6">
            <Link
              href="/"
              className="text-lg font-bold tracking-tight text-foreground transition-colors hover:text-primary"
            >
              SPACESCANS
            </Link>
            <nav className="hidden items-center gap-4 text-sm sm:flex">
              <Link
                href="/dashboard"
                className="text-muted-foreground transition-colors hover:text-foreground"
              >
                Dashboard
              </Link>
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-muted-foreground sm:inline">
              {email}
            </span>
            <ThemeToggle />
            <Separator orientation="vertical" className="h-5" />
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="gap-1.5 text-muted-foreground hover:text-foreground"
            >
              <LogOut className="size-4" />
              Log out
            </Button>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}
