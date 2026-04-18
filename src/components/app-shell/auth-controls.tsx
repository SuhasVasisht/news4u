"use client";

import { LogIn, LogOut } from "lucide-react";
import { signIn, signOut } from "next-auth/react";
import { Button } from "@/components/ui/button";

export function AuthControls({
  isAuthenticated,
  name,
}: {
  isAuthenticated: boolean;
  name: string | null;
}) {
  if (isAuthenticated) {
    return (
      <Button variant="secondary" onClick={() => void signOut({ callbackUrl: "/" })} className="gap-2">
        <LogOut className="h-4 w-4" />
        {name ? `Sign out ${name.split(" ")[0]}` : "Sign out"}
      </Button>
    );
  }

  return (
    <Button onClick={() => void signIn("google")} className="gap-2">
      <LogIn className="h-4 w-4" />
      Continue with Google
    </Button>
  );
}
