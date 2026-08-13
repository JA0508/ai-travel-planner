import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import "./road-movie.css";
import "./roadbook.css";

export const metadata: Metadata = {
  title: "旅程编辑部 | AI Trip Compiler",
  description: "把目的地、时间边界和固定安排编成一份看得懂、能调整的旅行路线。",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
