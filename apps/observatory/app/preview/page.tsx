import { permanentRedirect } from "next/navigation";

/** Legacy mock preview was removed: mobile now renders the real Observatory routes. */
export default function ObservatoryPreviewPage() {
  permanentRedirect("/");
}
