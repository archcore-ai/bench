---
title: Middleware conventions
status: accepted
tags: [middleware, http, conventions]
---

# Middleware conventions

Applies to `@middleware/`.

- All middleware lives in package `middleware`, one file per middleware: `middleware/<name>.go` plus a sibling `middleware/<name>_test.go`.
- Two canonical signatures are allowed:
  - No configuration: `func Name(next http.Handler) http.Handler`.
  - With configuration: `func Name(args ...T) func(http.Handler) http.Handler` — the constructor takes the config and returns the middleware.
- The returned handler always wraps the next handler and calls through:
  `return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { /* ... */ next.ServeHTTP(w, r) })`.
- Every exported middleware function carries a doc comment describing its behavior.
- Do not add new top-level dependencies for a middleware unless unavoidable; prefer the standard library.
