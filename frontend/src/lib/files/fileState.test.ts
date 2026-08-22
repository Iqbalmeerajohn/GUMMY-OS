import assert from "node:assert/strict";
import { test } from "node:test";

import { canReindex, fileState, type FileStateInput } from "./fileState.ts";

const file = (
  processing_status: FileStateInput["processing_status"],
  indexed_at: string | null = null,
): FileStateInput => ({ processing_status, indexed_at });

const INDEXED = "2026-08-22T09:00:00Z";

test("a completed file with embeddings is searchable", () => {
  assert.equal(fileState(file("completed", INDEXED)), "searchable");
});

test("a completed file without embeddings is not searchable", () => {
  // The regression this type exists to prevent: before embeddings, every
  // completed file rendered as Ready, so a user whose question returned nothing
  // could not tell whether the document lacked the answer or the index lacked
  // the document.
  assert.equal(fileState(file("completed")), "unindexed");
});

test("failure outranks a stale successful index", () => {
  // Re-indexing a previously indexed file can fail while `indexed_at` still
  // holds the earlier timestamp. Reporting that as searchable would hide the
  // regression behind old success.
  assert.equal(fileState(file("failed", INDEXED)), "failed");
});

test("in-flight files are distinguished from queued ones", () => {
  assert.equal(fileState(file("processing")), "processing");
  assert.equal(fileState(file("pending")), "pending");
});

test("re-indexing is offered only where it changes something", () => {
  assert.equal(canReindex("unindexed"), true);
  assert.equal(canReindex("failed"), true);
  // A searchable file needs no repair, and interrupting one mid-index would
  // only restart work already under way.
  assert.equal(canReindex("searchable"), false);
  assert.equal(canReindex("processing"), false);
  assert.equal(canReindex("pending"), false);
});
