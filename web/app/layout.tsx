import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bike Troubleshooting Assistant",
  description: "Manual-grounded AI troubleshooting for motorcycles.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
