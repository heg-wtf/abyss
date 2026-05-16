import type {
  ChatMessage,
  UploadedAttachment,
} from "@/lib/abyss-api";

export interface ConversationMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
  /**
   * Slash commands like ``/send`` return a downloadable file
   * alongside (or instead of) text. Mirrors the desktop chat-view
   * field so we render a download chip on the assistant bubble.
   */
  commandFile?: {
    name: string;
    path: string;
    url: string;
  } | null;
}

export interface PendingAttachment {
  localId: string;
  file: File;
  uploaded?: UploadedAttachment;
  uploading: boolean;
  error?: string;
}
