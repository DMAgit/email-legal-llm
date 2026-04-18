# Clause Library

## Liability - Acceptable Clause
clause_type: liability
risk_level: low
summary: A mutual twelve-month liability cap with standard carveouts is acceptable.

Clause text:
"Each party's aggregate liability under this agreement is limited to the fees paid or payable in the twelve months before the event giving rise to the claim. Neither party is liable for indirect, incidental, special, consequential, or punitive damages, except for confidentiality breaches, data security breaches, infringement indemnity, willful misconduct, and payment obligations."

Use guidance:
- Match to standard position.
- Supports auto_store when the rest of the contract is aligned.

## Liability - Negotiable Clause
clause_type: liability
risk_level: medium
summary: A six-month liability cap may be negotiable, but legal review is recommended if customer data is processed.

Clause text:
"Vendor's aggregate liability is limited to fees paid in the six months before the claim. Confidentiality breaches and infringement indemnity are excluded from the cap, but data security breaches are not listed as a carveout."

Use guidance:
- Route to legal review if customer data is processed.
- Otherwise treat as a non-standard liability position.

## Liability - Prohibited Clause
clause_type: liability
risk_level: high
summary: Customer-only liability and a one-month vendor cap conflict with internal policy.

Clause text:
"Customer is liable for all direct, indirect, consequential, incidental, special, exemplary, and punitive damages without limitation, including claims caused by vendor systems or vendor personnel. Vendor's total liability is capped at fees paid in the previous month."

Use guidance:
- Route to legal_review.

## Data Usage - Acceptable Clause
clause_type: data_usage
risk_level: low
summary: Data use is limited to service delivery and non-identifying aggregated statistics.

Clause text:
"Vendor may use customer data only to provide, secure, maintain, and support the services for Customer. Vendor may create aggregated usage statistics only if the statistics do not identify Customer, users, customers, or confidential business information. Vendor will not sell customer data or use it for unrelated products."

Use guidance:
- Match to standard approved data usage language.

## Data Usage - Negotiable Clause
clause_type: data_usage
risk_level: medium
summary: De-identified usage data for service reliability may be acceptable if safeguards and disclosures are present.

Clause text:
"Vendor may use de-identified usage data to improve service reliability and security. Vendor will not train artificial intelligence models on customer data without customer approval."

Use guidance:
- Generally acceptable only if de-identification controls and subprocessor disclosures are present.
- If supporting privacy documentation is missing, prefer manual_review.

## Data Usage - Prohibited Clause
clause_type: data_usage
risk_level: high
summary: AI training on customer data, prompts, outputs, or support content is prohibited.

Clause text:
"Vendor may use customer data, prompts, outputs, and support tickets to train, fine-tune, evaluate, or improve machine learning and artificial intelligence models, including models used for other customers. Vendor may share aggregated insights with partners."

Use guidance:
- Route to legal_review.

## Termination - Acceptable Clause
clause_type: termination
risk_level: low
summary: Mutual breach termination, customer convenience termination, and prompt data deletion are acceptable.

Clause text:
"Either party may terminate this agreement for material breach if the breach is not cured within 30 days after written notice. Customer may terminate hosted services for convenience on 30 days written notice. Upon termination, Vendor will return or delete customer data within 30 days."

Use guidance:
- Match to standard approved termination language.

## Termination - Negotiable Clause
clause_type: termination
risk_level: medium
summary: A 45-day cure period and no convenience termination may be negotiable in limited lower-risk cases.

Clause text:
"Either party may terminate for uncured material breach after 45 days written notice. Customer may terminate for convenience at the end of the then-current subscription period."

Use guidance:
- Negotiable when the vendor does not process customer data and fees are not prepaid.

## Termination - Prohibited Clause
clause_type: termination
risk_level: high
summary: Immediate vendor suspension, accelerated fees, and post-termination data retention require legal review.

Clause text:
"Vendor may suspend or terminate services immediately for any suspected breach, Customer must pay all fees for the remainder of the term, and Vendor may retain customer data for business purposes after termination."

Use guidance:
- Route to legal_review.

## Payment Terms - Acceptable Clause
clause_type: payment_terms
risk_level: low
summary: Monthly billing in arrears with Net 30 payment and good-faith dispute rights is acceptable.

Clause text:
"Vendor will invoice monthly in arrears. Invoices are due Net 30 after Customer receives a valid invoice. Customer may withhold disputed amounts in good faith while paying undisputed amounts on time."

Use guidance:
- Match to standard approved payment terms.

## Payment Terms - Negotiable Clause
clause_type: payment_terms
risk_level: medium
summary: Annual prepayment with Net 45 may be acceptable only with procurement review.

Clause text:
"Vendor will invoice annually in advance and invoices are due Net 45. Customer may dispute invoices in good faith."

Use guidance:
- Route to procurement_review if prepayment exceeds 25 percent of annual fees or if the vendor is not already approved.

## Payment Terms - Prohibited Clause
clause_type: payment_terms
risk_level: high
summary: Immediate payment on signature, non-refundable fees, service suspension during disputes, and unilateral price changes are unacceptable.

Clause text:
"Fees are due immediately on contract signature, are non-refundable in all cases, and Vendor may suspend services during any invoice dispute. Vendor may increase fees at any time on notice."

Use guidance:
- Route to procurement_review and consider legal_review depending on the surrounding terms.