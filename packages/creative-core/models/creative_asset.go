package core

type CreativeAsset struct {
    Identity map[string]any `json:"identity"`
    Source map[string]any `json:"source"`
    Content map[string]any `json:"content"`
    Visual map[string]any `json:"visual"`
    Pixel map[string]any `json:"pixel"`
    Style map[string]any `json:"style"`
    Animation map[string]any `json:"animation"`
    Engine map[string]any `json:"engine"`
    Quality map[string]any `json:"quality"`
    Provenance map[string]any `json:"provenance"`
    Version map[string]any `json:"version"`
}
