/** Plain explanations for the technical and legal terms the site uses (design brief, section 5). */
export const TERMS = {
  cfcfrms: {
    label: "CFCFRMS",
    text: "The Citizen Financial Cyber Fraud Reporting and Management System, run by the Ministry of Home Affairs (I4C). It sends banks notices to hold a victim's money and follows the money from bank to bank.",
  },
  ncrp: {
    label: "NCRP acknowledgement",
    text: "The 14-digit number a victim receives on reporting a cyber fraud: it starts with 2 for a complaint on cybercrime.gov.in and with 3 for a call to the 1930 helpline.",
  },
  lien: {
    label: "Lien",
    text: "A hold that stops a specific amount in an account from being spent. The rest of the account keeps working.",
  },
  layer: {
    label: "Layer",
    text: "How many transfers away from the victim an account is. The account that received the victim's payment is layer 1.",
  },
  tracedAmount: {
    label: "Traced amount",
    text: "How much of the money in an account is the victim's, worked out from the order of credits and debits under the rule in the MHA SOP: victims' money leaves before the account holder's own.",
  },
  debitHold: {
    label: "Temporary debit hold",
    text: "A hold on debits from a suspected mule account, with fixed deadlines for the customer, the bank and the police, under RBI's draft directions of September 2026.",
  },
  str: {
    label: "STR",
    text: "A suspicious transaction report that a bank files with FIU-IND under the Prevention of Money Laundering Act.",
  },
} as const;

export type TermKey = keyof typeof TERMS;
