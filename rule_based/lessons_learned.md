# Lessons Learned

This document reflects on the methodological strengths and limitations observed while
developing and evaluating the rule-based extraction pipeline for MRSA risk signals (see
[README.md](README.md) for the full pipeline description). It summarizes what the regex- and
lexicon-based approach handles well, where it fails, how its output should be
interpreted by clinical end users, and what should be prioritized in future iterations.
This version is based on the [`lexicons/mrsa_risk_factors_v3.csv`](lexicons/mrsa_risk_factors_v3.csv).

- [What worked well in rule-based extraction?](#what-worked-well-in-rule-based-extraction)
- [What were the hardest cases?](#what-were-the-hardest-cases)
- [How should clinicians use the extracted signals?](#how-should-clinicians-use-the-extracted-signals)
- [Suggestions for future work](#suggestions-for-future-work)

## What worked well in rule-based extraction?

- **Morphological matching for medications.** Rather than enumerating every brand and
  generic drug name individually, medication mentions can be captured through
  prefix/suffix regular expressions that target shared drug-class morphemes (e.g.,
  the "-cillin" suffix for penicillins, prefix "pred-" for corticosteroids). This
  generalizes matching to drug names not explicitly listed in the lexicon, at the cost
  of requiring careful validation that the matched substring is not a false positive
  from an unrelated word.

## What were the hardest cases?

Several categories of clinical language systematically challenged simple
keyword-and-regex matching:

- **Abbreviations.** Clinical shorthand is highly ambiguous and context-dependent
  (the same abbreviation can expand to different terms depending on the note type or
  specialty), making reliable expansion difficult with static lookup tables alone 
  (e.g. PD is short for Parkinson's Disease as well as Peritoneal Dialysis).
- **Multi-word terms.** Risk factors that are expressed as multi-token phrases (rather
  than single keywords) are more sensitive to variation in word order and intervening
  words within the note text.

Challenges associated to certain risk factors:

- **Planned or future procedures.** The rule set currently matches on keyword presence
  regardless of tense or clinical status, so a *planned* or *anticipated* procedure
  (not yet performed) is indistinguishable from one that has already occurred. This
  produces false positives for risk factors that should only count once realized.
  This does not apply when the keyword itself already encodes past tense (e.g.,
  "previous hospital stay"), since such terms are unambiguous about clinical status
  regardless of the rule set's lack of general tense handling.
- **Ambiguous facility references.** For example, a planned transfer to a skilled
  nursing facility (SNF) is currently recognized only via the keyword "SNF," which
  does not distinguish a *prospective* transfer from a *previous* SNF stay mentioned
  elsewhere in the note. Since prior SNF residence and planned SNF transfer carry
  different clinical and temporal meaning, conflating them can misrepresent a
  patient's actual exposure history.

## How should clinicians use the extracted signals?

Because the pipeline is presence-based (it extracts *whether* a keyword pattern
matched, not necessarily *when* or in *what clinical context*), extracted signals
should not all be trusted equally:

- **Higher confidence:** signals anchored to unambiguous, structured identifiers (e.g.,
  explicit ICD-10 codes or exact drug names) are generally more reliable, since they
  are less dependent on surrounding language.
- **Requires verification:** signals derived from free-text keyword matching alone —
  particularly where negation, tense, or planned-versus-completed status is relevant —
  should be spot-checked against the source note before being used to inform
  individual patient decisions.
- **Always check timeframe for non-persistent findings.** Events that are not
  permanent patient attributes (e.g., surgeries, bleeding episodes, catheter
  placement) should be manually reviewed for *when* they occurred relative to the
  encounter of interest, since the current extraction does not encode temporal
  distance between the note date and the event date.

## Suggestions for future work

- **Fuzzy matching for typos and spelling variants.** Currently, spelling variants are
  only covered to the extent that they have been explicitly added to the lexicon.
  Introduce a similarity-based matching step (e.g., Jaccard similarity) to catch misspellings of risk-factor terms that exact-match regex would otherwise miss. 
  - Apply this cautiously to abbreviations, since most are only two or three
    characters long and are especially prone to spurious fuzzy matches; consider
    restricting fuzzy matching to terms above a minimum length (e.g., > 3 characters).
  - Empirically test the similarity threshold (e.g., 80% vs. 90%) against a labeled
    sample to balance recall gains against introduced false positives.
- **Section- and context-aware extraction.** Rather than scanning the full note
  uniformly, restrict specific risk-factor keywords to the note sections where they
  are clinically meaningful (e.g., limit medication-class keywords to
  medication sections rather than the entire note/the allergy section), which should reduce
  cross-section false positives and enable note-type-specific rule sets.
