import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, LogIn, UserPlus } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  ApiError,
  getStoredAuthSession,
  loginWithPassword,
  registerWithPassword,
  requestPasswordReset,
  type AuthSession,
} from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

type AuthMode = "login" | "register" | "forgot";

export function AuthRoute() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [session, setSession] = useState<AuthSession | null>(() => getStoredAuthSession());

  const loginMutation = useMutation({
    mutationFn: loginWithPassword,
    onSuccess: () => {
      void queryClient.invalidateQueries();
      navigate("/");
    },
  });

  const registerMutation = useMutation({
    mutationFn: registerWithPassword,
    onSuccess: (result) => {
      void queryClient.invalidateQueries();
      if (result.session) {
        navigate("/");
        return;
      }
      setNotice("Confirmation email sent.");
      setMode("login");
      setPassword("");
    },
  });

  const forgotMutation = useMutation({
    mutationFn: requestPasswordReset,
    onSuccess: () => {
      setNotice("Password reset email requested.");
      setMode("login");
    },
  });

  const activeError = loginMutation.error ?? registerMutation.error ?? forgotMutation.error;
  const isBusy = loginMutation.isPending || registerMutation.isPending || forgotMutation.isPending;

  useEffect(() => {
    function updateSession() {
      setSession(getStoredAuthSession());
    }
    window.addEventListener("dossieragent-auth-changed", updateSession);
    window.addEventListener("storage", updateSession);
    return () => {
      window.removeEventListener("dossieragent-auth-changed", updateSession);
      window.removeEventListener("storage", updateSession);
    };
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    const redirectTo = `${window.location.origin}/auth`;
    if (mode === "login") {
      loginMutation.mutate({ email, password });
    } else if (mode === "register") {
      registerMutation.mutate({ email, password, displayName, redirectTo });
    } else {
      forgotMutation.mutate({ email, redirectTo });
    }
  }

  return (
    <div className="mx-auto grid max-w-3xl gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Auth</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>Supabase</span>
            <Badge variant="outline">Bearer JWT</Badge>
          </div>
        </div>
        <Select value={mode} onChange={(event) => setMode(event.target.value as AuthMode)}>
          <option value="login">Login</option>
          <option value="register">Register</option>
          <option value="forgot">Forgot password</option>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{titleForMode(mode)}</CardTitle>
          {mode === "login" ? (
            <LogIn className="size-4 text-primary" />
          ) : mode === "register" ? (
            <UserPlus className="size-4 text-primary" />
          ) : (
            <KeyRound className="size-4 text-primary" />
          )}
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={submit}>
            <label className="grid gap-1 text-xs font-medium uppercase text-muted-foreground">
              Email
              <Input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>

            {mode === "register" ? (
              <label className="grid gap-1 text-xs font-medium uppercase text-muted-foreground">
                Display name
                <Input
                  autoComplete="name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                />
              </label>
            ) : null}

            {mode !== "forgot" ? (
              <label className="grid gap-1 text-xs font-medium uppercase text-muted-foreground">
                Password
                <Input
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </label>
            ) : null}

            {notice ? (
              <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                {notice}
              </div>
            ) : null}
            {activeError ? <RouteError error={activeError} /> : null}

            <div className="flex flex-wrap gap-2 border-t pt-4">
              <Button
                type="submit"
                disabled={isBusy || !email || (mode !== "forgot" && !password)}
              >
                {mode === "login" ? (
                  <LogIn className="size-4" />
                ) : mode === "register" ? (
                  <UserPlus className="size-4" />
                ) : (
                  <KeyRound className="size-4" />
                )}
                {buttonForMode(mode)}
              </Button>
              {mode !== "login" ? (
                <Button type="button" variant="ghost" onClick={() => setMode("login")}>
                  Login
                </Button>
              ) : (
                <>
                  <Button type="button" variant="ghost" onClick={() => setMode("register")}>
                    Register
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setMode("forgot")}>
                    Forgot password
                  </Button>
                </>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {session ? (
        <Card>
          <CardHeader>
            <CardTitle>Current Session</CardTitle>
            <Badge variant="success">authenticated</Badge>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm">
            <div className="grid gap-1 sm:grid-cols-[140px_1fr]">
              <span className="text-muted-foreground">Email</span>
              <span className="font-medium">{session.user.email ?? "-"}</span>
            </div>
            <div className="grid gap-1 sm:grid-cols-[140px_1fr]">
              <span className="text-muted-foreground">App user</span>
              <span className="font-mono text-xs">{session.user.app_user_id}</span>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function titleForMode(mode: AuthMode) {
  if (mode === "register") return "Register";
  if (mode === "forgot") return "Forgot Password";
  return "Login";
}

function buttonForMode(mode: AuthMode) {
  if (mode === "register") return "Register";
  if (mode === "forgot") return "Request Reset";
  return "Login";
}

function RouteError({ error }: { error: Error }) {
  const message = error instanceof ApiError ? `${error.code}: ${error.message}` : error.message;
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
      {message}
    </div>
  );
}
