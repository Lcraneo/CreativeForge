package core

import "context"

type AssetProcessor interface {
    Name() string
    Version() string
    Process(context.Context, *CreativeAsset) (*CreativeAsset, error)
}
