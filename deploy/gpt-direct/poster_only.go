package main

import "net/http"

// The task worker receives an image-only capability, never the upstream's full API.
func posterOnly(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        allowed := r.Method == http.MethodGet && (r.URL.Path == "/healthz" || r.URL.Path == "/readyz" || r.URL.Path == "/v1/models")
        allowed = allowed || r.Method == http.MethodPost && r.URL.Path == "/v1/images/edits"
        if !allowed { http.NotFound(w, r); return }
        next.ServeHTTP(w, r)
    })
}
