import { AuthProvider } from "@/context/AuthContext";
import { AuthModalProvider } from "@/context/AuthModalContext";
import { ToastProvider } from "@/context/ToastContext";

export default function AppShellLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <AuthProvider>
      <AuthModalProvider>
        <ToastProvider>{children}</ToastProvider>
      </AuthModalProvider>
    </AuthProvider>
  );
}
