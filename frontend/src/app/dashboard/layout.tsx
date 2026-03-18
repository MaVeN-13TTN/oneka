import { DashboardProvider } from "@/components/dashboard/dashboard-provider";

export const metadata = {
  title: "Dashboard — Oneka",
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <DashboardProvider>{children}</DashboardProvider>;
}
