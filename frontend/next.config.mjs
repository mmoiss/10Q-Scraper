/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // Hardcoded for debugging
    const backendUrl = "https://10q-scraper-production.up.railway.app";

    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
