/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/events",
        destination: `${process.env.BACKEND_URL || "http://localhost:8000"}/events`,
      },
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL || "http://localhost:8000"}/:path*`,
      },
    ];
  },
};
export default nextConfig;
