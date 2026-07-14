import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export so the site can be served from S3 + CloudFront (no server).
  output: "export",
  // Required for static export since there is no Next.js image optimizer server.
  images: { unoptimized: true },
  // Emit each route as a directory with index.html, which maps cleanly to
  // S3/CloudFront object keys (e.g. /job/ -> /job/index.html).
  trailingSlash: true,
};

export default nextConfig;
