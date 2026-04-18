# Escalation Matrix

## Auto Store
clause_type: general
risk_level: low
summary: Auto-store is permitted only when policy alignment is confirmed, confidence is high, and vendor risk is low or approved.

Use auto_store only when all of the following are true:
- Retrieved policy context confirms that key terms align with the standard position.
- No policy conflicts are present.
- Extraction confidence is at least 0.80.
- Classifier confidence is at least 0.80.
- The vendor is approved or otherwise low risk.

Operational note:
- Auto-store candidates should still preserve retrieved context for traceability.

## Procurement Review
clause_type: general
risk_level: medium
summary: Use procurement_review for commercial or vendor-management risk that does not create a primary legal issue.

Examples:
- Net 60 payment terms.
- Annual prepayment above 25% of annual fees.
- Payment due on receipt.
- Uncapped renewal price increases.
- Renewal notice above 60 days.
- Non-standard billing cadence.
- Watchlist vendor status.
- Missing purchase order requirements.

Decision rule:
- If the core issue is commercial, pricing, billing, renewal, or vendor-management related, prefer procurement_review unless a separate legal trigger is also present.

## Legal Review
clause_type: general
risk_level: high
summary: Use legal_review for legal, privacy, security, or regulatory risk.

Examples:
- Unlimited liability.
- Uncapped indemnity.
- Customer-only liability.
- Prohibited AI training.
- Broad data sharing.
- Missing DPA.
- Foreign governing law.
- Vendor-only termination rights.
- Lack of data deletion rights.
- Retention of customer data after termination.

Decision rule:
- If both procurement_review and legal_review apply, choose legal_review.

## Manual Review
clause_type: general
risk_level: medium
summary: Use manual_review when confidence is too low, required context is missing, or the document cannot be reliably classified.

Examples:
- Extraction confidence is below 0.80.
- Retrieval returns no relevant policy context.
- Required clauses are missing.
- Retrieved context is contradictory.
- The vendor is blocked.
- The clause type is unknown.
- Model confidence is below 0.65.
- Business context is needed before choosing procurement_review or legal_review.

Decision rule:
- Manual review is appropriate when the system cannot confidently resolve the issue from the document and retrieved context alone.

## Tie Breaker Rules
clause_type: general
risk_level: medium
summary: Tie-breaker rules determine the final route when multiple conditions apply.

Rules:
- When both procurement_review and legal_review apply, choose legal_review.
- When policy context is missing or the classifier is uncertain, choose manual_review.
- When a vendor is blocked, do not auto_store.
- When the clause includes prohibited data usage, do not auto_store even if other terms are acceptable.