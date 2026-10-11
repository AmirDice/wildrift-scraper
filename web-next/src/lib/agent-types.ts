export type AgentSource = "data" | "model";

export interface AgentAction {
  label: string;
  href: string;
}

export interface AgentQuotaState {
  used: number;
  limit: number | null;
  remaining: number | null;
  signedIn: boolean;
  canUnlockBySigningIn: boolean;
  resetAt: number;
  unlimited?: boolean;
}

export interface AgentAnswer {
  answer: string;
  source: AgentSource;
  evidence?: string[];
  actions?: AgentAction[];
  followUps?: string[];
  quota?: AgentQuotaState;
}

export interface AgentHistoryMessage {
  role: "user" | "assistant";
  content: string;
}

