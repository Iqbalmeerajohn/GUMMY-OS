import type { MetadataRoute } from "next";

/**
 * Web app manifest — what makes GUMMY installable on a phone.
 *
 * The point is not novelty: a local-first assistant you can only reach from
 * the machine it runs on is a workstation tool. Installed to a home screen
 * and pointed at the backend over a tunnel, the same UI becomes the phone
 * client, with the model and the database still on your own hardware.
 *
 * `display: standalone` drops the browser chrome so it behaves like an app.
 * Two icon purposes are declared because Android masks icons to the device's
 * shape: the `maskable` variant keeps the mark inside the safe zone, while
 * `any` is used unmasked elsewhere. Shipping only one produces either a
 * cropped logo or a logo floating in a white square.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "GUMMY — Personal AI Operating System",
    short_name: "GUMMY",
    description:
      "Your local-first personal AI: persistent memory, goals and tasks, and collaborating agents — running on your own hardware.",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    // Matches the dark shell so the splash screen does not flash white.
    background_color: "#0f1413",
    theme_color: "#0f1413",
    categories: ["productivity", "utilities"],
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-maskable-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
