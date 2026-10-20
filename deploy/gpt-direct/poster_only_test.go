package main

import (
    "net/http"
    "net/http/httptest"
    "testing"
)

func TestPosterCapabilityOnlyAllowsRequiredRoutes(t *testing.T) {
    handler := posterOnly(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(204) }))
    for _, row := range []struct{ method, path string; status int }{
        {"GET", "/healthz", 204}, {"GET", "/readyz", 204}, {"GET", "/v1/models", 204},
        {"POST", "/v1/images/edits", 204},
        {"POST", "/v1/chat/completions", 404}, {"POST", "/v1/responses", 404},
        {"GET", "/v1/conversations/private/items", 404}, {"GET", "/v1/files", 404},
        {"GET", "/metrics", 404}, {"DELETE", "/v1/models", 404}, {"GET", "/v1/images/edits", 404},
    } {
        recorder := httptest.NewRecorder()
        handler.ServeHTTP(recorder, httptest.NewRequest(row.method, row.path, nil))
        if recorder.Code != row.status { t.Fatalf("%s %s: %d", row.method, row.path, recorder.Code) }
    }
}
