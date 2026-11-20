# Source documents

The five documents the agent answers from. `docs/` is the immutable raw layer: the ingest reads these
files and never edits them. A file whose hash differs from the one below is a different document, so
update the hash here in the same change.

| doc id | File | Title | Issuing body | Official URL | Retrieved | sha256 |
| --- | --- | --- | --- | --- | --- | --- |
| `gdpr` | `gdpr_regulation_2016_679.pdf` | Regulation (EU) 2016/679 (General Data Protection Regulation), Official Journal L 119, 4.5.2016 | European Parliament and Council of the European Union | open question | 2026-11-16 (file date as supplied) | `bd84e63f5b622b739a83389afc3b30d240f792bb88d8eb03a816c9a82b0c2499` |
| `hipaa` | `privacysummary.pdf` | Summary of the HIPAA Privacy Rule, OCR Privacy Brief (last revised 05/03) | US Department of Health and Human Services, Office for Civil Rights | open question | 2026-11-16 (file date as supplied) | `5d9b0ed5336cecffd0ab569d2315f5b6de6db0eff644f7b91dfcc6454a490111` |
| `ncsp` | `national_cyber_security_policy_2013.pdf` | National Cyber Security Policy 2013 | Government of India (the file does not name the ministry) | open question | 2026-11-16 (file date as supplied) | `eaf3dbcde254bad4739d687680cab2fcb741c417ca7c166f9991bc54a8276b5b` |
| `road_safety` | `national_road_safety_policy_2010.pdf` | National Road Safety Policy (Union Cabinet approval 15.03.2010) | Government of India (the file does not name the ministry) | open question | 2026-11-16 (file date as supplied) | `92ec49a8c49c76ef14c5801ee2633e9a0f1045c84b5a97750b53e1e85793110e` |
| `registration_api` | `customer_registration_api_spec.md` or `.pdf` | Customer Registration API specification | Another system's team; this repo holds a supplied copy | not applicable | not supplied yet | not supplied yet |

The files arrived under other names, listed here so the originals can be traced.

| File | Name as supplied |
| --- | --- |
| `gdpr_regulation_2016_679.pdf` | `CELEX_32016R0679_EN_TXT.pdf` |
| `privacysummary.pdf` | `privacysummary.pdf` |
| `national_cyber_security_policy_2013.pdf` | `National_cyber_security_policy-2013_0.pdf` |
| `national_road_safety_policy_2010.pdf` | `1754474627_Acts and Policies- National Road Safety Policy.pdf` |

The Customer Registration API spec belongs to a different system. It stays out of git (see
`.gitignore`) until its owning team agrees to a committed copy. Place it here as
`customer_registration_api_spec.md` (or `.pdf`) and add its sha256 to the table.
