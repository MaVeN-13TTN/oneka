"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function ForgotPasswordPage() {
  const router = useRouter();

  const handleForgotPassword = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    router.push("/login");
  };

  return (
    <main className="relative z-10 flex min-h-screen items-center justify-center px-6 py-12 md:px-10 md:py-16">
      <div className="mx-auto w-full max-w-md rounded-none border border-border bg-card/90 p-10 backdrop-blur sm:p-12">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          Oneka Access
        </p>
        <h1 className="mt-4 font-sans text-3xl font-bold tracking-tight">Forgot password</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Enter your email and we will send a reset link.
        </p>

        <form className="mt-12 space-y-7" onSubmit={handleForgotPassword}>
          <div className="space-y-2.5">
            <label htmlFor="forgot-password-email" className="text-sm font-medium">
              Email
            </label>
            <Input id="forgot-password-email" type="email" placeholder="you@example.com" required />
          </div>

          <Button type="submit" className="mt-3 h-11 w-full text-sm font-semibold">
            Send reset link
          </Button>
        </form>

        <p className="mt-10 text-center text-sm text-muted-foreground">
          Remembered your password?{" "}
          <Link href="/login" className="text-primary underline-offset-4 hover:underline">
            Back to login
          </Link>
        </p>

        <p className="mt-3 text-center text-sm text-muted-foreground">
          New here?{" "}
          <Link href="/signup" className="text-primary underline-offset-4 hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </main>
  );
}
