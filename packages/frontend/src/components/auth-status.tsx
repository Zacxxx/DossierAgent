import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LogIn, LogOut, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { getStoredAuthSession, logoutSession, type AuthSession } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function AuthStatus() {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<AuthSession | null>(() => getStoredAuthSession());

  const logoutMutation = useMutation({
    mutationFn: logoutSession,
    onSuccess: () => {
      setSession(null);
      void queryClient.invalidateQueries();
    },
  });

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

  if (!session) {
    return (
      <Button variant="outline" size="sm" asChild>
        <Link to="/auth">
          <LogIn className="size-4" />
          Login
        </Link>
      </Button>
    );
  }

  return (
    <div className="flex min-w-0 items-center gap-2">
      <Badge variant="outline" className="hidden max-w-[220px] truncate sm:inline-flex">
        <ShieldCheck className="size-3.5" />
        <span className="truncate">{session.user.email ?? session.user.app_user_id}</span>
      </Badge>
      <Button
        variant="ghost"
        size="sm"
        type="button"
        onClick={() => logoutMutation.mutate()}
        disabled={logoutMutation.isPending}
        title="Se deconnecter"
      >
        <LogOut className="size-4" />
        <span className="hidden md:inline">Logout</span>
      </Button>
    </div>
  );
}
