# BeeSafe AI — Phase 02 Chemical Identity Audit

Generated UTC: 2026-10-24T18:05:37.850665+00:00
Raw dataset SHA256: `de4b160a23601a44ac5ec5b23aae95973acba060135630a6df8f73d128baea9e`

- Records examined: **1035**
- RDKit-invalid SMILES: **0**
- Repeated CID groups: **5**
- Records flagged for review: **10**
- High-priority records: **4**
- Conflicting CID-label pairs: **2**
- PubChem live querying enabled: **True**

## Automated verification results

- CID_AND_STRUCTURE_MATCH_PUBCHEM: 4 records
- ALTERNATE_CID_STRUCTURE_MATCH_REVIEW: 4 records
- RECORDED_CID_STRUCTURE_MISMATCH_REVIEW: 2 records

## Decisions and limits

- No source rows, identifiers, or toxicity labels were changed.
- A PubChem CID/structure match validates only the matched public structure identifier, not toxicity measurement quality.
- Name/CAS lookup results can be ambiguous; alternate identifiers are suggestions, never automatic edits.
- Salt and fragment equivalence requires explicit scientific review.
- If the API was unavailable, corresponding verification remains incomplete.
- See the source-linked CSV for the precise evidence for each flagged record.

## References

- https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
- https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest-tutorial