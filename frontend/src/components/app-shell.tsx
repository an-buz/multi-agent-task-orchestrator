import { Sidebar } from "./sidebar";

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <main className="min-h-screen bg-background lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar />
      {children}
    </main>
  );
}
