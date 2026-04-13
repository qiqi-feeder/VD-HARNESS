import type { Metadata } from "next";
import { Inter, Geist_Mono, Share_Tech_Mono } from "next/font/google";
import { Toaster } from "sonner";
import "./globals.css";
import { QueryProvider } from "@/components/providers/query-provider";

const inter = Inter({
  variable: "--font-body",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

const shareTechMono = Share_Tech_Mono({
  variable: "--font-tech",
  weight: "400",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "VD-Flow — Open Source SuperAgent Harness",
  description: "An open-source SuperAgent harness that researches, codes, and creates. With sandboxes, memories, tools, skills and subagents.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${geistMono.variable} ${shareTechMono.variable} h-full antialiased dark`}
    >
      <body className="min-h-full flex flex-col">
        <QueryProvider>{children}</QueryProvider>
        <Toaster
          position="bottom-right"
          theme="dark"
          toastOptions={{
            style: {
              background: "rgba(28,28,35,0.7)",
              border: "1px solid rgba(255,255,255,0.15)",
              color: "var(--foreground)",
              boxShadow: "0 16px 48px rgba(0, 0, 0, 0.6)",
              backdropFilter: "blur(24px)",
            },
          }}
        />
      </body>
    </html>
  );
}
