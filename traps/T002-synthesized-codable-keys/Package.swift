// swift-tools-version: 5.9
// Trap T002: renaming a CodingKeys raw value changes the JSON that synthesized `encode(to:)` writes.
// StorageTests never spells CodingKeys or the key, yet it fails after the edit. See trap.json.
import PackageDescription

let package = Package(
    name: "T002SynthesizedCodableKeys",
    targets: [
        .target(name: "Core"),
        .target(name: "Storage", dependencies: ["Core"]),
        .target(name: "Labels", dependencies: ["Core"]),
        .testTarget(name: "StorageTests", dependencies: ["Storage"]),
        .testTarget(name: "LabelsTests", dependencies: ["Labels"]),
    ]
)
