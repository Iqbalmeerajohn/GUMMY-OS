import type { FileItem } from "@/lib/api/resources";

/**
 * What a file can actually do for the user, as opposed to what happened to it.
 *
 * The backend reports `processing_status`, which describes the pipeline:
 * whether text was extracted and chunked. That is not the question the user is
 * asking. They want to know whether GUMMY can answer from this document, and
 * those two things came apart the moment embeddings were added — a file
 * uploaded before that layer existed is `completed` with no embeddings, so it
 * reads as ready and answers nothing.
 *
 * `indexed_at` is the field that separates them, and this is the only place
 * that decision is made.
 */
export type FileState =
  | "searchable"
  | "unindexed"
  | "processing"
  | "pending"
  | "failed";

/** Narrowed to the fields the decision actually depends on, so tests need no fixtures. */
export type FileStateInput = Pick<FileItem, "processing_status" | "indexed_at">;

export function fileState(file: FileStateInput): FileState {
  // Failure first: a file that failed after a previous successful index still
  // carries the old `indexed_at`, and reporting it as searchable would hide the
  // regression behind stale success.
  if (file.processing_status === "failed") return "failed";
  if (file.indexed_at) return "searchable";
  if (file.processing_status === "completed") return "unindexed";
  return file.processing_status === "processing" ? "processing" : "pending";
}

/** Whether re-indexing this file would do anything useful. */
export function canReindex(state: FileState): boolean {
  return state === "unindexed" || state === "failed";
}
