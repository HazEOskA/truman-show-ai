/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone"
  // The API address is deliberately *not* declared here. Anything under `env` is inlined at
  // build time, which welds one image to one API. `app/layout.tsx` reads HYDRA_API_URL on the
  // server at request time instead, so the same image runs locally and on Cloud Run.
};

export default nextConfig;
