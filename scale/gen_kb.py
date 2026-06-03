#!/usr/bin/env python3
"""Generate a scalable, multi-domain Archcore knowledge base for the token benchmark.

Each document encodes ONE normative, non-guessable fact (a "convention") whose answer
is a unique token buried in the body, so answering requires actually reading the doc.

Honesty invariants:
  * Answer token is arbitrary => arm A (cold) cannot guess it.
  * Topic phrase (the search target) appears ONLY in title + Context; the token appears
    ONLY in Decision + Example, far below => a content-search match yields a title/Context
    excerpt WITHOUT the token => get_document/read is genuinely required (archcore lazy-load).
  * Docs are realistically sized (~700 tokens: a real ADR/rule with Context / Decision /
    Consequences / Alternatives / Example / References) so preload cost is not understated.
    Per-doc size is printed so reviewers can audit it.
  * Docs interleaved across domains by doc_id => any prefix of size N is multi-domain.
  * Deterministic (seeded).

Env: NDOCS (default 320) controls how many docs to generate (multiple of 5).
Outputs: kb/<domain>/<slug>.<type>.md  and  facts.csv
"""
import csv
import os
import random
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(HERE, "kb")
FACTS = os.path.join(HERE, "facts.csv")
SEED = 42
NDOCS = int(os.environ.get("NDOCS", "320"))

# domain -> (type, tag, slot-name shown in the question, slot clause template embedding {tok})
DOMAINS = {
    "middleware": ("rule", "middleware", "middleware registration group id",
                   "registered in the middleware group `{tok}`"),
    "routing":    ("rule", "routing", "route mount prefix",
                   "mounted under the route prefix `{tok}`"),
    "errors":     ("adr",  "errors", "sentinel error identifier",
                   "represented by the sentinel error `{tok}`"),
    "logging":    ("rule", "logging", "structured log field key",
                   "logged under the structured field key `{tok}`"),
    "testing":    ("rule", "testing", "build tag",
                   "guarded by the build tag `{tok}`"),
}
DOMAIN_ORDER = list(DOMAINS.keys())

BASE_TOPICS = {
    "middleware": ["request id propagation", "panic recovery", "CORS preflight handling",
                   "gzip response compression", "request body size limit", "auth token extraction",
                   "rate limiting", "per request timeout budget", "real client IP resolution",
                   "CSRF protection", "content negotiation", "structured access logging",
                   "trace span injection", "maintenance mode gating", "feature flag gating",
                   "request throttling"],
    "routing": ["health check endpoints", "API version namespacing", "route group composition",
                "path parameter parsing", "trailing slash normalization", "method not allowed handling",
                "subrouter mounting", "static asset serving", "redirect rules",
                "named route registration", "wildcard route matching", "host based routing",
                "endpoint deprecation sunset", "per route metrics", "canary traffic routing",
                "websocket upgrade handling"],
    "errors": ["sentinel error definitions", "error wrapping chains", "HTTP status mapping",
               "request validation errors", "panic to error conversion", "error response envelope",
               "client versus server errors", "retryable error classification", "domain error catalog",
               "context cancellation errors", "upstream timeout errors", "not found handling",
               "write conflict handling", "rate limit rejection errors", "error event logging",
               "error rate metrics"],
    "logging": ["log level policy", "structured field naming", "correlation id logging",
                "request access logging", "sensitive data redaction", "high volume log sampling",
                "security audit logging", "log serialization format", "error log enrichment",
                "slow dependency logging", "log file rotation", "distributed trace id logging",
                "span id logging", "log shipping destination", "debug log gating",
                "metric extraction from logs"],
    "testing": ["table driven test layout", "integration build tagging", "golden file fixtures",
                "httptest server usage", "shared test fixtures", "race detector policy",
                "coverage threshold gate", "slow test gating", "interface mock generation",
                "test function naming", "subtest organization", "benchmark conventions",
                "flaky test quarantine", "test data directory", "parallel test execution",
                "test http client reuse"],
}


def expand_topics(domain, count):
    """Distinct topic phrases. The first 16 are the real base topics (used as task
    targets). Filler beyond 16 uses a SEPARATE vocabulary that never contains a base
    phrase as a substring, so a content-search for any base/task topic returns exactly
    the one target doc (no collision artifact as N grows)."""
    base = BASE_TOPICS[domain]
    out = list(base)
    # filler nouns disjoint from base topic wording
    fillers = ["retention policy", "quota schedule", "shard placement", "buffer sizing",
               "drain procedure", "warmup routine", "backpressure guard", "checkpoint cadence",
               "lease renewal", "compaction window", "eviction order", "fanout limit"]
    k = len(base)
    while len(out) < count:
        idx = len(out)
        f = fillers[(idx) % len(fillers)]
        out.append("{} subsystem {} {}".format(domain, idx, f))  # e.g. "middleware subsystem 80 retention policy"
    return out[:count]


def slugify(s):
    return s.replace(" ", "-").replace("/", "-").lower()


def make_token(rng, domain):
    pfx = {"middleware": "mwg", "routing": "rt", "errors": "Err",
           "logging": "fld", "testing": "tag"}[domain]
    code = "".join(rng.choice("0123456789abcdefghijklmnopqrstuvwxyz") for _ in range(4))
    if domain == "routing":
        return "/" + pfx + code
    if domain == "errors":
        return pfx + code.upper()
    return "{}_{}".format(pfx, code)


# ~700-token realistic doc. topic phrase: title + Context only. token: Decision + Example only.
DOC_BODY = """---
title: {title}
status: accepted
tags: [{tags}]
---

# {title}

## Context

{topic} is exercised on nearly every request path in this service, and over time
several teams implemented it slightly differently. The resulting drift made
incidents harder to debug: dashboards keyed off one spelling, runbooks off another,
and on-call engineers wasted time reconciling them during outages. We want a single
canonical convention for {topic} so that tooling, alerts, and code review can all
assume the same shape without per-team negotiation.

## Decision

We standardize {topic}. The convention is binding for all packages under this area.

RULE: it MUST be {slot_clause}. This value is fixed project-wide; do not introduce
alternatives, aliases, or per-environment overrides. Pull requests that diverge from
it should be rejected in review, and any pre-existing divergence should be migrated.

## Consequences

Tooling, dashboards, and on-call runbooks can rely on a single stable identifier
instead of guessing per service or per team. New services inherit the convention for
free by following this document. The trade-off is reduced local flexibility: a team
that wants a different shape must first amend this decision rather than diverging
silently, which is intentional friction.

## Alternatives considered

- Leave it to each team. Rejected: this is exactly the drift that caused the incidents
  above, and it makes cross-service tooling impossible to write reliably.
- Infer the value at runtime from configuration. Rejected: it moves a compile-time
  guarantee into runtime config, where it can silently diverge across environments.

## Example

In practice the {slot} `{tok}` is wired in during setup; see
`{domain}/{slug}.go`, where `{tok}` is applied to the {topic} path. Code review should
check for that exact value.

## References

- Internal incident review that motivated this convention.
- The service-wide conventions index.
"""


def main():
    rng = random.Random(SEED)
    if os.path.isdir(KB):
        shutil.rmtree(KB)
    os.makedirs(KB)

    per = NDOCS // len(DOMAIN_ORDER)
    topics = {d: expand_topics(d, per) for d in DOMAIN_ORDER}

    rows = []
    seen = set()
    sizes = []
    for i in range(NDOCS):
        domain = DOMAIN_ORDER[i % len(DOMAIN_ORDER)]
        within = i // len(DOMAIN_ORDER)
        topic = topics[domain][within]
        dtype, tag, slot, slot_tpl = DOMAINS[domain]

        tok = make_token(rng, domain)
        while tok in seen:
            tok = make_token(rng, domain)
        seen.add(tok)

        slug = slugify(topic)
        rel = "{}/{}.{}.md".format(domain, slug, dtype)
        title = topic[0].upper() + topic[1:]
        kws = [w for w in topic.split() if w not in ("policy", "area")][:2]
        tags = ", ".join([tag] + kws)

        body = DOC_BODY.format(
            title=title, tags=tags, domain=domain, topic=topic,
            slot=slot, slot_clause=slot_tpl.format(tok=tok), slug=slug, tok=tok)
        path = os.path.join(KB, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(body)
        sizes.append(len(body))

        question = ("According to the project's documented conventions, what is the exact "
                    "{slot} for {topic}? Reply with only the value, nothing else.").format(
            slot=slot, topic=topic)
        rows.append({"doc_id": "{:03d}".format(i), "domain": domain, "type": dtype,
                     "path": rel, "title": title, "topic": topic, "slot": slot,
                     "question": question, "answer_token": tok, "search_term": topic})

    with open(FACTS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    avg_chars = sum(sizes) / len(sizes)
    print("generated {} docs across {} domains ({} per domain) -> {}".format(
        NDOCS, len(DOMAIN_ORDER), per, KB))
    print("avg doc size: {:.0f} chars (~{:.0f} tokens)".format(avg_chars, avg_chars / 4))
    print("facts -> {}".format(FACTS))


if __name__ == "__main__":
    main()
