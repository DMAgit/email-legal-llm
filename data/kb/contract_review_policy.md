# Contract Review Policy

## Payment Terms - Standard Position
clause_type: payment_terms
risk_level: low
summary: Preferred payment terms are Net 30 or Net 45 after receipt of a valid invoice, with billing in arrears and preserved invoice dispute rights.

Standard position:
- Preferred payment terms are Net 30 or Net 45 after receipt of a valid invoice.
- Invoices should be billed in arrears unless a signed order form expressly approves prepayment.
- Payment obligations should be conditioned on receipt of a valid invoice, tax documentation, and purchase order details where required.
- Customer should retain the right to dispute invoices in good faith while paying undisputed amounts on time.

Expected indicators:
- "Net 30"
- "Net 45"
- "valid invoice"
- "billed in arrears"
- "good-faith invoice dispute"

Example acceptable language:
"Vendor will invoice monthly in arrears. Invoices are due Net 30 after Customer receives a valid invoice. Customer may withhold disputed amounts in good faith while paying undisputed amounts on time."

## Payment Terms - Procurement Review Triggers
clause_type: payment_terms
risk_level: medium
summary: Net 60, annual prepayment, aggressive billing mechanics, and unfavorable invoice terms require procurement review.

Review triggers:
- Net 60 payment terms.
- Annual prepayment.
- Milestone billing without acceptance criteria.
- Auto-charge provisions.
- Late fees above 1.5% per month.
- Payment due on receipt.
- Prepayment above 25% of annual fees unless the vendor is already approved for that commercial model.

Example review language:
"Fees are invoiced annually in advance and due Net 60."

## Payment Terms - Prohibited Positions
clause_type: payment_terms
risk_level: high
summary: Payment obligations before signature, waived dispute rights, unilateral price changes, and suspension during disputes should not be accepted without escalation.

Prohibited positions:
- Payment before contract signature.
- Waiver of invoice dispute rights.
- Unilateral vendor price changes during a committed term.
- Service suspension while a good-faith invoice dispute is pending.

Example prohibited language:
"Fees are due immediately on signature and Vendor may suspend services during any billing dispute."

## Liability - Standard Cap
clause_type: liability
risk_level: low
summary: Standard contracts should include a mutual liability cap tied to fees paid or payable in the previous twelve months.

Standard position:
- Aggregate liability should be capped at the greater of fees paid or payable in the previous twelve months.
- Mutual liability caps are preferred.
- Exclusions should cover indirect, incidental, special, consequential, exemplary, and punitive damages.

Example acceptable language:
"Each party's aggregate liability under this agreement is limited to the fees paid or payable in the twelve months before the event giving rise to the claim."

## Liability - Carveouts
clause_type: liability
risk_level: low
summary: Certain liability carveouts are acceptable when they are mutual where the underlying risk applies to both parties.

Acceptable carveouts:
- Confidentiality breaches.
- Data security breaches caused by the vendor.
- Gross negligence.
- Willful misconduct.
- Infringement indemnity.
- Payment obligations.

Guidance:
- Carveouts should be mutual where the risk applies to both parties.
- Carveouts should not be drafted in a way that creates customer-only exposure.

## Liability - Legal Review Triggers
clause_type: liability
risk_level: high
summary: Unlimited liability, uncapped indemnity, low vendor caps, or customer-only exposure require legal review.

Legal review triggers:
- Unlimited liability.
- Uncapped indemnity.
- Customer-only liability exposure.
- Consequential damages exposure.
- Exclusion of vendor confidentiality liability.
- Vendor liability capped below six months of fees.
- Any clause making the customer responsible for third-party claims caused by the vendor.

Example prohibited language:
"Customer shall indemnify Vendor for all third-party claims and Vendor's total liability shall not exceed one month of fees."

## Data Usage - Standard Position
clause_type: data_usage
risk_level: low
summary: Vendor may use customer data only to provide, secure, support, and improve the contracted services for the customer.

Standard position:
- Vendor may process customer data only to provide, secure, support, and improve the contracted services for the customer.
- Aggregated analytics are acceptable only when they cannot identify the company, users, customers, or confidential business information.

Example acceptable language:
"Vendor may process customer data only to provide and secure the services and may create aggregated metrics that do not identify Customer or individuals."

## Data Usage - AI Restrictions
clause_type: data_usage
risk_level: high
summary: Vendor use of customer data, prompts, outputs, logs, or confidential information for AI training is prohibited unless legal approves explicit written language.

Restricted uses:
- Training AI models.
- Fine-tuning AI models.
- Evaluating AI models.
- Improving AI models.
- Using prompts, outputs, support tickets, logs, telemetry, customer data, personal data, or confidential information for cross-customer model improvement.

Required disclosures before approval:
- AI subprocessors.
- Model hosting.
- Prompt logging.
- Human review of prompts or outputs.

Example prohibited language:
"Vendor may use customer data, prompts, outputs, and support tickets to train and improve artificial intelligence models used across vendor products."

## Data Usage - Privacy and Security Requirements
clause_type: data_usage
risk_level: high
summary: Contracts involving personal data must include core privacy and security terms; missing privacy protections require legal review.

Required terms:
- Data processing agreement.
- Subprocessor disclosure.
- Security controls.
- Breach notice.
- Data deletion rights.
- Audit or assurance evidence such as SOC 2 Type II, ISO 27001, or equivalent.

Legal review triggers:
- Missing privacy terms.
- Missing data deletion rights.
- Missing subprocessor disclosure when personal data is involved.

## Termination - Standard Position
clause_type: termination
risk_level: low
summary: Contracts should allow termination for material breach with a 30-day cure period and should preserve post-termination data return or deletion rights.

Standard position:
- Termination for material breach if the breach is not cured within 30 days after written notice.
- For SaaS, hosted tools, or vendors handling customer data, termination for convenience on 30 days notice is preferred.
- Vendor should return or delete customer data after termination.

Example acceptable language:
"Either party may terminate for uncured material breach after 30 days notice, and Vendor will delete or return customer data within 30 days after termination."

## Termination - Legal Review Triggers
clause_type: termination
risk_level: high
summary: Vendor-only termination rights, immediate suspension, termination fees, broad survival language, or retention of customer data require legal review.

Legal review triggers:
- Vendor-only termination rights.
- Immediate suspension without notice.
- Termination fees.
- Survival of broad payment obligations after termination.
- Loss of data export rights.
- Vendor retention of customer data after termination.

Example prohibited language:
"Vendor may suspend or terminate services immediately for suspected breach and Customer must pay all fees through the end of the term."

## Renewal - Standard Position
clause_type: renewal
risk_level: low
summary: Automatic renewal is acceptable only with a notice period of 60 days or less and controlled renewal pricing.

Standard position:
- Automatic renewal is acceptable only when non-renewal notice is 60 days or less.
- Renewal pricing should be capped or clearly disclosed.
- Renewal terms should preserve existing legal protections, data processing terms, and security obligations.

Example acceptable language:
"The subscription renews automatically for successive one-year terms unless either party gives notice at least 30 days before renewal, and renewal pricing will not exceed the agreed schedule."

## Renewal - Procurement Review Triggers
clause_type: renewal
risk_level: medium
summary: Long renewal notice periods, uncapped price increases, evergreen terms, or list-price renewals require procurement review.

Review triggers:
- Renewal notice periods above 60 days.
- Uncapped renewal price increases.
- Evergreen terms.
- Renewal pricing tied only to vendor list price.
- Automatic renewal after a trial.

Example review language:
"The subscription renews automatically unless either party gives notice at least 90 days before renewal. Renewal fees may increase to Vendor's then-current list price."

## Governing Law - Preferred Jurisdictions
clause_type: governing_law
risk_level: low
summary: Preferred governing law is Delaware, New York, California, England and Wales, or the company's home jurisdiction.

Preferred positions:
- Delaware.
- New York.
- California.
- England and Wales.
- The company's home jurisdiction.
- Neutral commercial arbitration may be acceptable for international vendors if injunctive relief remains available for confidentiality and intellectual property breaches.

## Governing Law - Legal Review Triggers
clause_type: governing_law
risk_level: high
summary: Foreign governing law outside preferred jurisdictions, vendor-friendly forums, or limits on emergency remedies require legal review.

Legal review triggers:
- Foreign governing law outside preferred jurisdictions.
- Exclusive venue in a vendor-friendly forum.
- Waiver of injunctive relief.
- Class action waiver tied to consumer terms.
- Mandatory arbitration that limits emergency remedies.

Example prohibited language:
"This agreement is governed by the laws of a non-preferred foreign jurisdiction and all disputes must be brought exclusively in Vendor's local courts."