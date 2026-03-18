"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="size-4">
      <path
        fill="#EA4335"
        d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.9-5.5 3.9-3.3 0-6-2.7-6-6s2.7-6 6-6c1.9 0 3.2.8 3.9 1.5l2.7-2.6C16.9 3.2 14.7 2.2 12 2.2 6.6 2.2 2.2 6.6 2.2 12S6.6 21.8 12 21.8c6.9 0 9.6-4.8 9.6-7.3 0-.5-.1-.9-.1-1.3H12z"
      />
      <path
        fill="#34A853"
        d="M3.3 7.4 6.5 9.7c.9-2.1 3-3.6 5.5-3.6 1.9 0 3.2.8 3.9 1.5l2.7-2.6C16.9 3.2 14.7 2.2 12 2.2 8.1 2.2 4.8 4.4 3.3 7.4z"
      />
      <path
        fill="#FBBC05"
        d="M12 21.8c2.6 0 4.8-.8 6.5-2.3l-3-2.4c-.8.6-1.9 1-3.5 1-2.5 0-4.6-1.6-5.4-3.8l-3.2 2.5c1.5 3 4.8 5 8.6 5z"
      />
      <path
        fill="#4285F4"
        d="M21.6 14.5c.1-.4.2-.9.2-1.4 0-.5-.1-.9-.1-1.3H12v3.9h5.5c-.3 1.4-1.1 2.4-2 3.1l3 2.4c1.7-1.6 3.1-4 3.1-6.7z"
      />
    </svg>
  );
}

export default function SignupPage() {
  const router = useRouter();

  const handleSignup = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    router.push("/dashboard");
  };

  const handleGoogleSignup = () => {
    router.push("/dashboard");
  };

  return (
    <main className="relative z-10 flex min-h-screen items-center justify-center px-6 py-12 md:px-10 md:py-16">
      <div className="mx-auto w-full max-w-md rounded-none border border-border bg-card/90 p-10 backdrop-blur sm:p-12">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
          Oneka Access
        </p>
        <h1 className="mt-4 font-sans text-3xl font-bold tracking-tight">Create account</h1>
        <p className="mt-2 text-sm text-muted-foreground">Start auditing infrastructure from space.</p>

        <form className="mt-12 space-y-7" onSubmit={handleSignup}>
          <div className="space-y-2.5">
            <label htmlFor="signup-email" className="text-sm font-medium">
              Email
            </label>
            <Input id="signup-email" type="email" placeholder="you@example.com" required />
          </div>

          <div className="space-y-2.5">
            <label htmlFor="signup-password" className="text-sm font-medium">
              Password
            </label>
            <Input id="signup-password" type="password" placeholder="Create a password" required minLength={8} />
          </div>

          <Button type="submit" className="mt-3 h-11 w-full text-sm font-semibold">
            Sign up
          </Button>
        </form>

        <div className="my-9 flex items-center gap-4">
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs uppercase tracking-[0.14em] text-muted-foreground">or</span>
          <div className="h-px flex-1 bg-border" />
        </div>

        <Button
          type="button"
          variant="outline"
          className="h-11 w-full justify-center gap-2 text-sm"
          onClick={handleGoogleSignup}
        >
          <GoogleIcon />
          Continue with Google
        </Button>

        <p className="mt-10 text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="text-primary underline-offset-4 hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}
