import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Empty turbopack config to silence warning
  turbopack: {},
  webpack: (config, { isServer }) => {
    // Handle web workers
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
      };
    }
    return config;
  },
};

export default nextConfig;
