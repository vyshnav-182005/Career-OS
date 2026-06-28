import type { Metadata } from "next";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: "CareerOS — AI-Powered Career Guidance Platform",
  description:
    "CareerOS analyzes your profile, matches you with the best jobs, and generates ATS-optimized resumes tailored to every job description.",
  keywords: ["career guidance", "AI resume", "job matching", "ATS resume", "career platform"],
  openGraph: {
    title: "CareerOS — AI-Powered Career Guidance Platform",
    description:
      "Analyze your profile, discover matching jobs, and generate ATS-optimized resumes with AI.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>{children}</body>
    </html>
  );
}
