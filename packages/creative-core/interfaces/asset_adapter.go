package core

type AssetAdapter interface {
    Name() string
    Version() string
    CanHandle(string) bool
    Import(any) (*CreativeAsset, error)
    Export(*CreativeAsset) (any, error)
}
