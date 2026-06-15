"use client";

import { Check, ChevronDown } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AGENT_MODES, AUTO } from "@/lib/chat/routing";
import { cn } from "@/lib/utils";

/**
 * Dark, glass-themed agent selector (replaces the OS-native <select>, which
 * couldn't be themed). Auto is the recommended default; manual agents are
 * grouped separately under "Manual Testing".
 */
export function AgentSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const current = AGENT_MODES.find((m) => m.value === value)?.label ?? "Auto";
  const manual = AGENT_MODES.filter((m) => m.value !== AUTO);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="glass hover:border-primary/40 inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-sm transition-colors">
        <span className="text-muted-foreground text-xs">Agent</span>
        <span className="font-medium">{current}</span>
        <ChevronDown className="text-muted-foreground size-3.5" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60">
        <p className="text-muted-foreground px-2 py-1 text-[11px] tracking-wide">
          Auto Agent Mode (Recommended)
        </p>
        <Option
          label="Auto"
          selected={value === AUTO}
          onSelect={() => onChange(AUTO)}
        />
        <DropdownMenuSeparator />
        <p className="text-muted-foreground px-2 py-1 text-[11px] tracking-wide">
          Manual Testing
        </p>
        {manual.map((m) => (
          <Option
            key={m.value}
            label={m.label}
            selected={value === m.value}
            onSelect={() => onChange(m.value)}
          />
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Option({
  label,
  selected,
  onSelect,
}: {
  label: string;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <DropdownMenuItem onClick={onSelect} className="justify-between">
      {label}
      <Check
        className={cn("size-3.5", selected ? "opacity-100" : "opacity-0")}
      />
    </DropdownMenuItem>
  );
}
