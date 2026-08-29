import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Hydra World — Command Observatory",
  description: "Live command surface for the deterministic Hydra World simulation"
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
    <html lang="en">
      <head>
        <script
          // JSON.stringify escapes the value, so a hostile env var cannot break out of the
          // script tag it is written into.
          dangerouslySetInnerHTML={{
            __html: `window.__HYDRA_API_URL__=${JSON.stringify(api)};`
          }}
        />
      </head>
      <body>
        <Suspense
          fallback={(
            <div className="shell shell--observatory">
              <main className="main">{children}</main>
            </div>
          )}
        >
          <AppShell>{children}</AppShell>
        </Suspense>
      </body>
    </html>
  );
}
