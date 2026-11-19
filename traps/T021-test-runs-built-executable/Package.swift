// swift-tools-version: 5.9
// Trap T021: GreetTests runs the built `greet` executable as a process and checks its output. It has no
// dependency on the executable target, so no edge in the package graph links them. See trap.json.
import PackageDescription

let package = Package(
    name: "T021TestRunsBuiltExecutable",
    targets: [
        .target(name: "Words"),
        .executableTarget(name: "greet", dependencies: ["Words"]),
        .testTarget(name: "GreetTests"),
        .testTarget(name: "WordsTests", dependencies: ["Words"]),
    ]
)
