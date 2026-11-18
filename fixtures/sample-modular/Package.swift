// swift-tools-version: 5.9
// The worked example from docs/method.md: one shared models module, two features, one app module.
import PackageDescription

let package = Package(
    name: "SampleModular",
    products: [
        .library(name: "AppCore", targets: ["AppCore"]),
    ],
    targets: [
        .target(name: "Models"),
        .target(name: "CharacterFeature", dependencies: ["Models"]),
        .target(name: "EpisodeFeature", dependencies: ["Models"]),
        .target(name: "AppCore", dependencies: ["Models", "CharacterFeature", "EpisodeFeature"]),
        .testTarget(name: "ModelsTests", dependencies: ["Models"]),
        .testTarget(name: "CharacterFeatureTests", dependencies: ["CharacterFeature"]),
        .testTarget(name: "EpisodeFeatureTests", dependencies: ["EpisodeFeature"]),
        .testTarget(name: "AppCoreTests", dependencies: ["AppCore"]),
    ]
)
