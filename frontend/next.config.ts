import type { NextConfig } from "next";

const nextConfig: NextConfig = {
	output: "standalone",
};

if (process.env.NODE_ENV === "development") {
	nextConfig.rewrites = async () => [
		{
			source: "/api/:path*",
			destination: `${process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000"}/api/:path*`,
		},
	];
}

export default nextConfig;
