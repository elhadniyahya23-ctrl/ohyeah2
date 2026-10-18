import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Phantom User Sniper | Username Checker",
  description:
    "Phantom User Sniper — high-speed username checker for Discord, Roblox, Minecraft, and more.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full antialiased">{children}</body>
    </html>
  );
}
