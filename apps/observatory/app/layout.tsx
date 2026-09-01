import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./observatory-mobile.css";
import "./observatory-mobile-home.css";
import "./observatory-mobile-full.css";
import "./observatory-mobile-device.css";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "HYDRA WORLD OBSERVATORY",
  description: "Autonomiczny świat na żywo — obserwatorium i panel sterowania Hydra World"
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover"
};

/**
 * Never cache this shell: it carries the runtime API address, and a cached copy would pin
 * every visitor to whichever API the first render happened to see.
 */
export const dynamic = "force-dynamic";

/**
 * The API address is read here, on the server, at request time.
 *
 * `NEXT_PUBLIC_*` is inlined when the bundle is built, so a built image can only ever talk
 * to one API. On Cloud Run the API's URL does not exist until it has been deployed, which
 * would mean building the front end twice. Reading a plain server-side variable and handing
 * it to the browser makes one image deployable anywhere.
 */
function apiUrl(): string {
  return (
    process.env.HYDRA_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const api = apiUrl();
  return (
    <html lang="pl">
      <head>
        <meta name="hydra-commit" content={process.env.HYDRA_COMMIT_SHA || "unknown"} />
        <meta name="hydra-revision" content={process.env.K_REVISION || "unknown"} />
        <script
          // JSON.stringify escapes the value, so a hostile env var cannot break out of the
          // script tag it is written into.
          dangerouslySetInnerHTML={{
            __html: `window.__HYDRA_API_URL__=${JSON.stringify(api)};`
          }}
        />
      </head>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
