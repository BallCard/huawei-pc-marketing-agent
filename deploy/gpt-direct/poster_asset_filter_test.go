package chatgpt

import (
    "reflect"
    "testing"
)

func TestImageInputsCannotBecomeGeneratedOutput(t *testing.T) {
    var got Event
    filter := withoutInputImages(func(e Event) error {got=e; return nil}, map[string]bool{"product-input":true,"style-input":true})
    filter(Event{AssetPointers:[]string{"file-service://product-input","sediment://style-input","file-service://generated-output"}})
    if !reflect.DeepEqual(got.AssetPointers, []string{"file-service://generated-output"}) {t.Fatal("reference image leaked into generated outputs")}
    filter(Event{AssetPointers:[]string{"file-service://style-input"}})
    if len(got.AssetPointers)!=0 {t.Fatal("input-only reply claimed a generated asset")}
}
