/**
 * Chat contracts — multimodal-ready extension points (M3 preparation).
 *
 * IMPORTANT: these are TYPES + a capability registry only. No functionality is
 * implemented here. M3 builds text chat against these contracts; voice, image,
 * PDF, and video plug in later WITHOUT reshaping the message model — the chat
 * system must never assume text-only.
 */

export type ChatModality = "text" | "voice" | "image" | "pdf" | "video";

/** A single piece of message content. Text is the only active modality today. */
export interface ChatContentPart {
  modality: ChatModality;
  /** Text body (modality: "text") or a transcript/caption for other modalities. */
  text?: string;
  /** Reference to an uploaded asset (modality: image/pdf/video/voice). */
  attachment?: ChatAttachment;
}

export interface ChatAttachment {
  id: string;
  modality: Exclude<ChatModality, "text">;
  /** Storage URL or signed reference (resolved by the future asset layer). */
  url?: string;
  mimeType?: string;
  name?: string;
  sizeBytes?: number;
  /** Optional extracted/derived text (e.g. PDF text, transcript). */
  extractedText?: string;
}

export type ChatRole = "user" | "assistant" | "system";

/** What the user submits for a turn — always a list of parts, never a bare string. */
export interface ChatMessageInput {
  role: "user";
  parts: ChatContentPart[];
}

/** A persisted/rendered message. */
export interface ChatMessage {
  id: string;
  role: ChatRole;
  parts: ChatContentPart[];
  createdAt: string;
}

export interface ModalityCapability {
  modality: ChatModality;
  /** Whether the modality is usable now. Only text ships in M3. */
  enabled: boolean;
  /** User-facing note for disabled modalities (Planned Evolution). */
  note?: string;
}

/** The capability registry the composer reads to enable/disable inputs. */
export const MODALITY_CAPABILITIES: ModalityCapability[] = [
  { modality: "text", enabled: true },
  { modality: "voice", enabled: false, note: "Voice interaction is planned." },
  { modality: "image", enabled: false, note: "Image intelligence is planned." },
  {
    modality: "pdf",
    enabled: false,
    note: "Document understanding is planned.",
  },
  { modality: "video", enabled: false, note: "Video intelligence is planned." },
];

/** Convenience: build a text-only input (the M3 path). */
export function textInput(text: string): ChatMessageInput {
  return { role: "user", parts: [{ modality: "text", text }] };
}
