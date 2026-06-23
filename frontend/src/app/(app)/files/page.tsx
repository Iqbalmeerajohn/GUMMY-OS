import type { Metadata } from "next";

import { FilesCenter } from "@/components/files/FilesCenter";

export const metadata: Metadata = {
  title: "Files",
};

/**
 * Files — upload documents into GUMMY's knowledge system, view the library, and
 * manage files (Phase 4 · M6 Files System).
 */
export default function FilesPage() {
  return <FilesCenter />;
}
