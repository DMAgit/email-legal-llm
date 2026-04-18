# Legal Playbook

## Missing Clauses
clause_type: general
risk_level: medium
summary: Missing key clauses should not be treated as acceptable by default.

Guidance:
- If a contract lacks liability, data usage, termination, renewal, or governing law language, do not infer that the terms are acceptable.
- Missing key clauses should produce manual_review unless the document is a low-risk order form that clearly incorporates an approved master agreement.

Operational signal:
- If the uploaded document contains pricing but no meaningful legal terms, lower confidence and prefer manual_review.

## Order Forms and Incorporated Terms
clause_type: general
risk_level: medium
summary: Incorporated terms are only useful if they are present in parsed text or retrieved context.

Guidance:
- Order forms may rely on a master services agreement, data processing addendum, or online terms.
- If the incorporated agreement is not present in the parsed text or retrieved context, classify with lower confidence and prefer manual_review.
- If the incorporated agreement is approved and current, use its terms to resolve the risk level.

Operational signal:
- References to "online terms", "master agreement", "DPA", or "security addendum" without attached text should reduce confidence.

## AI Vendor Claims
clause_type: data_usage
risk_level: high
summary: AI vendor language about improvement, analytics, logging, or quality review may conceal prohibited model training.

Guidance:
- Treat language involving prompts, outputs, support tickets, logs, telemetry, feedback, or customer data as data_usage context.
- If the clause allows model training without explicit customer approval, route to legal_review.

Example suspicious language:
- "service improvement"
- "quality review"
- "model improvement"
- "usage analytics"
- "support optimization"

## De-Identified and Aggregated Data
clause_type: data_usage
risk_level: medium
summary: Aggregated or de-identified data language is acceptable only when re-identification and sharing risks are controlled.

Guidance:
- De-identified or aggregated data language is acceptable only when the clause states that the data cannot identify the company, users, customers, or confidential business information.
- If re-identification controls are absent or the vendor can share insights with third parties, route to legal_review or manual_review depending on specificity.

Operational signal:
- If the clause says "aggregated insights may be shared with partners", treat this as elevated risk.

## Security Evidence Missing
clause_type: data_usage
risk_level: medium
summary: Missing privacy and security evidence should reduce confidence and may require legal review.

Guidance:
- When a vendor processes personal data or customer confidential information, missing SOC 2, ISO 27001, penetration test summary, breach notice, or security exhibit should reduce confidence.
- Use manual_review if no specific policy conflict is found.
- Use legal_review if the contract also lacks privacy or data deletion rights.

## Negotiation Guidance - Liability
clause_type: liability
risk_level: medium
summary: Request a mutual twelve-month liability cap and preserve the standard carveouts.

Guidance:
- Start by requesting a mutual liability cap equal to fees paid or payable in the previous twelve months.
- Preserve carveouts for confidentiality, data security breaches, infringement indemnity, willful misconduct, and payment obligations.
- Reject customer-only caps and vendor caps below six months of fees.

## Negotiation Guidance - Data Usage
clause_type: data_usage
risk_level: high
summary: Data usage should be limited to service delivery and should prohibit AI training without explicit approval.

Guidance:
- Ask the vendor to limit customer data use to providing, securing, supporting, and maintaining the contracted services.
- Add a sentence prohibiting use of customer data, prompts, outputs, support tickets, logs, or telemetry to train or improve AI models without explicit written approval.

## Negotiation Guidance - Termination
clause_type: termination
risk_level: medium
summary: Request mutual breach termination, convenience termination for hosted services, and post-termination data handling terms.

Guidance:
- Request mutual termination for material breach with a cure period of 30 days or less.
- For hosted services, request termination for convenience on 30 days notice.
- Require clear data return or deletion obligations after termination.

## Negotiation Guidance - Payment Terms
clause_type: payment_terms
risk_level: medium
summary: Request Net 30 or Net 45 after valid invoice receipt and preserve dispute rights.

Guidance:
- Ask for Net 30 or Net 45 after receipt of a valid invoice.
- Ask for billing in arrears.
- Preserve good-faith invoice dispute rights.
- If the vendor insists on annual prepayment, route to procurement_review and request service credits or refund rights for termination caused by vendor breach.

## Negotiation Guidance - Renewal
clause_type: renewal
risk_level: medium
summary: Automatic renewal notice should be 60 days or less and renewal pricing should be controlled.

Guidance:
- Limit automatic renewal notice to 60 days or less.
- Require renewal price increases to be capped, stated in the order form, or subject to written customer approval.
- Do not accept evergreen renewal language without procurement review.

## Negotiation Guidance - Governing Law
clause_type: governing_law
risk_level: medium
summary: Prefer core approved jurisdictions and preserve emergency injunctive relief in international disputes.

Guidance:
- Request Delaware, New York, California, England and Wales, or the company's home jurisdiction.
- For international vendors, neutral arbitration may be acceptable if emergency injunctive relief remains available for confidentiality, intellectual property, and data protection claims.