"use client";

import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/auth/AuthProvider";
import {
  deleteFile,
  fetchFileStats,
  fetchFiles,
  reindexFile,
  uploadFile,
  type FileItem,
} from "@/lib/api/resources";
import { analytics, AnalyticsEvent } from "@/lib/analytics";

const FILES_KEY = ["files", "all"] as const;
const STATS_KEY = ["files", "stats"] as const;

/**
 * The user's uploaded files (newest first). Single source of truth; every file
 * surface reads this query so the Files page and dashboard widget stay in sync.
 */
export function useFilesQuery() {
  const { user } = useAuth();
  return useQuery({
    queryKey: FILES_KEY,
    queryFn: async (): Promise<FileItem[]> => {
      const page = await fetchFiles({ limit: 100 });
      return page.items;
    },
    enabled: !!user,
    retry: false,
  });
}

/** Total file count + recent files (dashboard widget + page header). */
export function useFileStats() {
  const { user } = useAuth();
  return useQuery({
    queryKey: STATS_KEY,
    queryFn: fetchFileStats,
    enabled: !!user,
    retry: false,
  });
}

/**
 * Upload + delete actions, backed by the API and stable across renders. Each
 * successful mutation invalidates the files queries (so the page + dashboard
 * refetch) and records the matching event through the analytics seam.
 */
export function useFileActions() {
  const qc = useQueryClient();
  // Invalidating the `files` root covers the list and stats queries.
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["files"] });
  };
  const onError = (err: unknown) => {
    analytics.captureException(err, { context: "file_action_failed" });
    toast.error(err instanceof Error ? err.message : "Something went wrong.");
  };

  const upload = useMutation({
    mutationFn: (file: File) => uploadFile(file),
    onSuccess: (file) => {
      analytics.track(AnalyticsEvent.FileUploaded, {
        file_id: file.id,
        mime_type: file.mime_type,
        size_bytes: file.size_bytes,
      });
      if (file.processing_status === "completed") {
        analytics.track(AnalyticsEvent.FileProcessed, {
          file_id: file.id,
          chunk_count: file.chunk_count,
        });
        toast.success(`"${file.original_filename}" uploaded.`);
      } else if (file.processing_status === "failed") {
        toast.error(
          `"${file.original_filename}" uploaded, but processing failed.`,
        );
      }
      invalidate();
    },
    onError,
  });

  const reindex = useMutation({
    mutationFn: (id: string) => reindexFile(id),
    onSuccess: (file) => {
      // Re-indexing is the recovery path, so its outcome has to be stated
      // plainly. Silently returning a still-broken file is how a user ends up
      // asking the same unanswerable question twice.
      if (file.indexed_at) {
        toast.success(`"${file.original_filename}" is searchable.`);
      } else if (file.processing_status === "failed") {
        toast.error(
          `"${file.original_filename}" could not be indexed.` +
            (file.error_message ? ` ${file.error_message}` : ""),
        );
      } else {
        toast.info(`"${file.original_filename}" is being indexed.`);
      }
      invalidate();
    },
    onError,
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteFile(id),
    onSuccess: (_void, id) => {
      analytics.track(AnalyticsEvent.FileDeleted, { file_id: id });
      invalidate();
    },
    onError,
  });

  return useMemo(
    () => ({
      upload: (file: File) => upload.mutateAsync(file),
      remove: (id: string) => remove.mutate(id),
      reindex: (id: string) => reindex.mutate(id),
      isUploading: upload.isPending,
      reindexingId: reindex.isPending ? reindex.variables : null,
    }),
    [upload, remove, reindex],
  );
}
