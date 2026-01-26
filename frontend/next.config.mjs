/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'export',
    // Disable image optimization for static export
    images: {
        unoptimized: true,
    },
    // Trailing slash helps with static file serving
    trailingSlash: true,
};

export default nextConfig;
