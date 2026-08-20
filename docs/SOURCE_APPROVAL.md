# New-source approval boundary

SecureSwipe cannot infer dataset origin from numeric rows. A copied, reordered,
deduplicated, or reserialized historical corpus can look like a different file.
New model decisions therefore require an operator-reviewed approval JSON bound
to the exact source bytes. This is a human attestation and audit record—not a
cryptographic proof that the reviewer is correct.

The approval must contain exactly:

```json
{
  "approval_format_version": "1",
  "approved_file_sha256": "<64 lowercase hex characters>",
  "attestation": "I attest that this exact file is authorized for development and contains no rows derived from the already-observed SecureSwipe historical corpus.",
  "reviewed_by": "<accountable human reviewer>",
  "source_reference": "<owner-controlled immutable source/version reference>"
}
```

Compute the source checksum locally with `shasum -a 256 /path/to/source.csv`.
Review the data origin, write the JSON outside the raw-data directory, and pass
it with `--source-approval`. Changing one source byte, attestation character, or
reference invalidates the approval. Do not use credentials, tokens, or customer
identifiers as the reviewer/reference fields.

Project-created historical curation outputs retain `historical_taint` in their
verified record and are refused as new sources when that lineage accompanies the
CSV. Copying the CSV away from its record destroys detectable lineage, so the
reviewer must not approve such a derivative. Real deployments should replace
this reference attestation with their governed data catalog/lineage authority.
