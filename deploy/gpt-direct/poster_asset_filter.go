package chatgpt

import "strings"

// Uploaded reference pointers are input, never proof that a new image exists.
func withoutInputImages(emit func(Event) error, inputs map[string]bool) func(Event) error {
    return func(event Event) error {
        if len(event.AssetPointers) != 0 {
            filtered := make([]string, 0, len(event.AssetPointers))
            for _, pointer := range event.AssetPointers {
                id := strings.TrimPrefix(strings.TrimPrefix(pointer, "file-service://"), "sediment://")
                if !inputs[id] { filtered = append(filtered, pointer) }
            }
            event.AssetPointers = filtered
        }
        return emit(event)
    }
}
