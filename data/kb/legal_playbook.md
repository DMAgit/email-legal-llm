# Legal Playbook

## Edge Case - Missing Clauses

If a contract lacks liability, data usage, termination, renewal, or governing law
language, do not infer that the terms are acceptable. Missing key clauses should
produce manual_review unless the contract is a low-risk order form that clearly
incorporates an approved master agreement.

## Edge Case - Order Forms and Incorporated Terms

Order forms may rely on a master services agreement, data processing addendum,
or online terms. If the incorporated agreement is not present in the parsed text
or retrieved context, classify with lower confidence and prefer manual_review.
If the incorporated agreement is approved and current, use its terms to resolve
the risk level.

## Edge Case - AI Vendor Claims

AI vendors may describe model improvement, service improvement, analytics, or
quality review in ways that obscure training rights. Treat language involving
prompts, outputs, support tickets, logs, telemetry, feedback, or customer data
as data_usage context. If the clause allows model training without explicit
customer approval, route to legal_review.

## Edge Case - De-Identified and Aggregated Data

De-identified or aggregated data language is acceptable only when the clause
states that the data cannot identify the company, users, customers, or
confidential business information. If re-identification controls are absent or
the vendor can share insights with third parties, route to legal_review or
manual_review depending on specificity.

## Edge Case - Security Evidence Missing

When a vendor processes personal data or customer confidential information,
missing SOC 2, ISO 27001, penetration test summary, breach notice, or security
exhibit should reduce confidence. Use manual_review if no specific policy
conflict is found, and legal_review if the contract also lacks privacy or data
deletion rights.

## Negotiation Guidance - Liability

Start by requesting a mutual liability cap equal to fees paid or payable in the
previous twelve months. Preserve carveouts for confidentiality, data security
breaches, infringement indemnity, willful misconduct, and payment obligations.
Reject customer-only caps and vendor caps below six months of fees.

## Negotiation Guidance - Data Usage

Ask the vendor to limit customer data use to providing, securing, supporting,
and maintaining the contracted services. Add a sentence prohibiting use of
customer data, prompts, outputs, support tickets, logs, or telemetry to train or
improve AI models without explicit written approval.

## Negotiation Guidance - Termination

Request mutual termination for material breach with a cure period of 30 days or
less. For hosted services, request termination for convenience on 30 days notice
and clear data return or deletion obligations after termination.

## Negotiation Guidance - Payment Terms

Ask for Net 30 or Net 45 after receipt of a valid invoice, billing in arrears,
and good-faith invoice dispute rights. If the vendor insists on annual
prepayment, route to procurement_review and request service credits or refund
rights for termination caused by vendor breach.

## Negotiation Guidance - Renewal

Limit automatic renewal notice to 60 days or less. Require renewal price
increases to be capped, stated in the order form, or subject to written customer
approval. Do not accept evergreen renewal language without procurement review.

## Negotiation Guidance - Governing Law

Request Delaware, New York, California, England and Wales, or the company's home
jurisdiction. For international vendors, neutral arbitration may be acceptable
if emergency injunctive relief remains available for confidentiality,
intellectual property, and data protection claims.
