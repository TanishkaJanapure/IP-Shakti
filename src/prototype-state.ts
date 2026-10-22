export type Jurisdiction = "India" | "International";

export type InterfaceLanguage =
  | "English"
  | "हिन्दी"
  | "தமிழ்"
  | "বাংলা"
  | "తెలుగు"
  | "मराठी";

export type AssistantState =
  | "sample"
  | "empty"
  | "loading"
  | "insufficient"
  | "error";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  state: "sample" | "loading" | "error";
};

export type CitationRecord = {
  id: string;
  number: number;
  title: string;
  section: string;
  authority: string;
  effectiveDate: string;
  sourceUrl: string | null;
  verification: "placeholder" | "verified";
};

export type FormulationAnswers = {
  intendedUse: string;
  productDescription: string;
  ingredients: string;
  formulationType: string;
  traditionalText: string;
  textReference: string;
  innovation: string[];
  claimType: string;
  claims: string;
  dosageForm: string;
  market: string;
};

export type AbsAnswers = {
  resourceName: string;
  resourceType: string;
  originCountry: string;
  originState: string;
  sourceMethod: string;
  activity: string[];
  activityDetails: string;
  userCategory: string;
  organisationName: string;
  foreignParticipation: string;
  traditionalKnowledge: string;
  knowledgeDetails: string;
  communityIdentified: string;
  commercialisation: string;
  exportPlan: string;
  destination: string;
};

export type ResearchState = "results" | "empty" | "loading" | "no-results" | "error";

export type SearchFilters = {
  jurisdiction: "All jurisdictions" | Jurisdiction;
  documentType: string;
  publicationDate: string;
  documentStatus: string;
};

export type RetrievedCitationState = {
  query: string;
  filters: SearchFilters;
  status: ResearchState;
  selectedRecordId: string | null;
  recordsAreVerified: boolean;
};

export type PrototypeFrontendState = {
  jurisdiction: Jurisdiction;
  language: InterfaceLanguage;
  chatMessages: ChatMessage[];
  formulationAnswers: FormulationAnswers;
  absAnswers: AbsAnswers;
  research: RetrievedCitationState;
};

// This contract describes UI state only. Retrieval, evidence verification,
// legal classification, ingestion, and LLM responses belong to the FastAPI backend.
