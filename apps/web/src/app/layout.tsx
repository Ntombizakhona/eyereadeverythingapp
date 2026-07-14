import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "eyereadeverything — Blog to Video, Voice to Video",
  description: "Transform blog posts and voice ideas into YouTube-ready video packages powered by Amazon Nova AI.",
  keywords: ["AI video", "blog to video", "Amazon Nova", "YouTube automation", "content creation"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="animated-bg" />
        <nav className="navbar">
          <div className="navbar-inner">
            <Link href="/" className="logo">eyereadeverything</Link>
            <div className="nav-links">
              <Link href="/blog" className="nav-link">Blog → Video</Link>
              <Link href="/text" className="nav-link">Text → Video</Link>
              <Link href="/talk" className="nav-link">Talk → Video</Link>
              <Link href="/dashboard" className="nav-link">Dashboard</Link>
            </div>
          </div>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
