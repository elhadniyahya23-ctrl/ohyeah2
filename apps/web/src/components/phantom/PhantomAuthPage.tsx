"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { AmbientBackground } from "@/components/phantom/AmbientBackground";
import { AuthChrome } from "@/components/phantom/AuthChrome";
import { DiscordBadge } from "@/components/phantom/DiscordBadge";
import { NavIconSprite } from "@/components/phantom/NavIcons";

interface Props {
  children: ReactNode;
}

export function PhantomAuthPage({ children }: Props) {
  useEffect(() => {
    document.body.classList.add("phantom-auth");
    return () => document.body.classList.remove("phantom-auth");
  }, []);

  return (
    <>
      <NavIconSprite />
      <AmbientBackground />
      <DiscordBadge />
      <AuthChrome />
      <div className="screen active" id="screen-login">
        {children}
      </div>
    </>
  );
}
