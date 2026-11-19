// swift-tools-version: 5.9
// Trap T013: a default argument value is compiled into each caller. Changing it in Core changes what an
// unchanged call in Greeting passes, though no public signature's shape changes. See trap.json.
import PackageDescription

let package = Package(
    name: "T013DefaultArgumentValue",
    targets: [
        .target(name: "Core"),
        .target(name: "Greeting", dependencies: ["Core"]),
        .target(name: "Reports", dependencies: ["Core"]),
        .testTarget(name: "GreetingTests", dependencies: ["Greeting"]),
        .testTarget(name: "ReportsTests", dependencies: ["Reports"]),
    ]
)
