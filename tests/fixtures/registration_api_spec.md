# Sample Registration API

This synthetic document stands in for the real specification. It holds no real service content.

## Duplicate detection

An incoming customer is compared with stored customers on a normalized key.

```text
# this line looks like a heading but sits inside a code fence
key = normalize(value)
```

After the fence the section text continues.

## Fuzzy screening

A model scores the remaining candidates.

### Timeout

A screening call that exceeds its limit falls back to the exact comparison.

### Candidate cap

A fixed number of candidates is sent in each call.
