# Escalation Matrix

## auto_store

Use auto_store only when retrieved policy context confirms that key terms align
with the standard position, no policy conflicts are present, extraction
confidence is at least 0.80, classifier confidence is at least 0.80, and the
vendor is approved or low risk. Auto-store candidates should still preserve
retrieved context for traceability.

## procurement_review

Use procurement_review for commercial or vendor-management risk that does not
create a primary legal issue. Examples include Net 60 terms, annual prepayment
above 25% of annual fees, payment due on receipt, uncapped renewal price
increases, renewal notice above 60 days, non-standard billing cadence, watchlist
vendor status, or missing purchase order requirements.

## legal_review

Use legal_review for legal, privacy, security, or regulatory risk. Examples
include unlimited liability, uncapped indemnity, customer-only liability,
prohibited AI training, broad data sharing, missing DPA, foreign governing law,
vendor-only termination rights, lack of data deletion rights, or retention of
customer data after termination.

## manual_review

Use manual_review when extraction confidence is below 0.80, retrieval returns
no relevant policy context, required clauses are missing, retrieved context is
contradictory, the vendor is blocked, the clause type is unknown, or the model
confidence is below 0.65. Manual review is also appropriate when business
context is needed before choosing procurement_review or legal_review.

## Tie Breaker Rules

When both procurement_review and legal_review apply, choose legal_review. When
policy context is missing or the classifier is uncertain, choose manual_review.
When a vendor is blocked or the clause includes prohibited data usage, do not
auto_store even if other terms are acceptable.
