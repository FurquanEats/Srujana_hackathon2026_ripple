/** The grievance officer's evidence packs (scripts/capture_review_fixtures.py), in ripple_review's shapes. */
export type Quoted = { value: string | null; quote: string | null; page: number | null };

export type Extraction = {
  readable: boolean;
  document_type: Quoted;
  issuer: Quoted;
  issuer_gstin: Quoted;
  recipient: Quoted;
  recipient_latin: string | null;
  number: Quoted;
  date: Quoted;
  taxable_value: Quoted;
  total: Quoted;
  payment_reference: Quoted;
};

export type ReviewDocument = {
  file: string;
  url: string;
  language: string;
  form: string;
  quality: string;
  extraction: Extraction | null;
};

export type HeldCredit = {
  credit_id: string;
  rail: string;
  reference: string;
  amount: number;
  at: string;
  remitter: { name: string; ifsc: string | null; account_number: string | null };
  traced_amount: number;
};

export type CreditVerdict = {
  credit_id: string;
  verdict: "explained" | "partly_explained" | "not_explained" | "conflicting";
  explained_amount: number;
  unexplained_amount: number;
  document: string | null;
  proposed_action: "lift" | "reduce" | "keep";
  hold_after: number;
  failed_checks: string[];
  reasons: string[];
};

export type ReviewPack = {
  case_id: string;
  title: string;
  holder: {
    name: string;
    address?: string;
    account_number: string;
    ifsc: string;
    gstin?: string | null;
    kyc: {
      occupation?: string;
      business_type?: string;
      declared_annual_turnover?: number | null;
      declared_annual_income?: number | null;
    };
  };
  explanation: string | null;
  credits: HeldCredit[];
  tds_rate_percent: number | null;
  documents: ReviewDocument[];
  read: boolean;
  verdicts: CreditVerdict[];
  model: string;
};
