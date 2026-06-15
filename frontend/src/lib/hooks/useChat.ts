"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/components/auth/AuthProvider";
import {
  createConversation,
  listConversations,
  listMessages,
  postTurn,
} from "@/lib/api/resources";

export function useConversations() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["conversations", "list"],
    queryFn: () => listConversations(30),
    enabled: !!user,
    retry: false,
  });
}

export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => listMessages(conversationId!),
    enabled: !!conversationId,
    retry: false,
  });
}

export function useCreateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentContext: string) => createConversation(agentContext),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useSendTurn() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      conversationId,
      message,
    }: {
      conversationId: string;
      message: string;
    }) => postTurn(conversationId, message),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["messages", vars.conversationId] });
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}
