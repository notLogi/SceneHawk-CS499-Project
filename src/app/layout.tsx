import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { Playfair_Display, Inter } from "next/font/google";
import "./globals.css";

const playfair = Playfair_Display({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--font-playfair",
});
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3001",
  ),
  title: {
    default: "SceneHawk",
    template: "%s · SceneHawk",
  },
  description:
    "Describe the film you want to feel. SceneHawk searches by atmosphere, pacing, and visual language — not genre, rating, or what you watched last.",
  openGraph: {
    title: "SceneHawk",
    description:
      "Multi-agent film discovery — search by atmosphere, pacing, and visual language.",
    images: ["/scenehawk.png"],
  },
};

const NAV = [
  { label: "Home", href: "/" },
  { label: "Discover", href: "/search" },
  { label: "Chat", href: "/chat" },
  { label: "Analysis", href: "/catalog" },
  { label: "Collections", href: "/collections" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${playfair.variable} ${inter.variable}`}>
      <body className="min-h-screen antialiased">
        <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-5 md:px-10 py-4">
          <Link href="/" aria-label="SceneHawk home" className="shrink-0">
            <Image
              src="/scenehawk.png"
              alt="SceneHawk"
              width={270}
              height={180}
              className="h-16 w-auto md:h-20 -my-4 md:-my-6"
              priority
            />
          </Link>
          <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs sm:text-sm text-[#b7b2a7]">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className="hover:text-[#ece7df] transition-colors"
              >
                {n.label}
              </Link>
            ))}
            <button
              type="button"
              title="Accounts aren't part of the MVP — placeholder"
              className="rounded-full bg-[#e0632f] px-4 py-1.5 sm:px-5 sm:py-2 font-medium text-[#0a0a0a] hover:bg-[#ea7443] transition-colors"
            >
              Sign in
            </button>
          </nav>
        </header>
        <main className="mx-auto max-w-6xl px-5 md:px-10 pb-24">
          {children}
        </main>
      </body>
    </html>
  );
}
