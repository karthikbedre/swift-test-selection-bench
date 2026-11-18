// swift-tools-version: 5.9
// Trap T003: a new stored property joins the synthesized Hashable conformance, so two tags that were
// equal no longer are. CatalogTests never spells the property, yet it fails after the edit. See trap.json.
import PackageDescription

let package = Package(
    name: "T003SynthesizedHashableProperty",
    targets: [
        .target(name: "Core"),
        .target(name: "Catalog", dependencies: ["Core"]),
        .target(name: "Shelf", dependencies: ["Core"]),
        .testTarget(name: "CatalogTests", dependencies: ["Catalog"]),
        .testTarget(name: "ShelfTests", dependencies: ["Shelf"]),
    ]
)
