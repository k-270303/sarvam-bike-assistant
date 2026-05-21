export type ApiErrorDetail = {
  code?: string;
  message?: string;
};

export type SessionResponse = {
  session_id: string;
};

export type IngestResponse = {
  session_id: string;
  documents: string[];
  pages_processed: number;
  chunks_indexed: number;
  warnings: string[];
};

export type Citation = {
  document_name: string;
  page_start: number;
  page_end: number;
  section_title: string;
  excerpt: string;
};

export type VisionObservation = {
  visible_observations: string[];
  visible_text: string[];
  visible_components: string[];
  uncertainties: string[];
};

export type TroubleshootResponse = {
  status: "success" | "clarification_needed" | "low_confidence";
  issue_summary?: string | null;
  possible_cause?: string | null;
  recommended_action?: string | null;
  confidence_score: number;
  confidence_level: "high" | "medium" | "low";
  citations: Citation[];
  safety_warning?: string | null;
  escalation_recommendation?: string | null;
  clarification_questions: string[];
  message?: string | null;
  vision_observation?: VisionObservation;
  vision_warning?: string;
  enriched_query?: string;
};

export type TranscribeResponse = {
  transcript: string;
};
