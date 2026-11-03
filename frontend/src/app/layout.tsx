import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Capability Analysis | Student Insights",
  description: "Complexity-aware capability analysis, cohort placement, and learning recommendations.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
