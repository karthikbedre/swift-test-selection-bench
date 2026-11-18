// swift-tools-version: 5.9
// Trap T004: a new, more specific overload in Core wins overload resolution at an existing call site in
// Billing. Nothing in Billing changes, yet BillingTests fails after the edit. See trap.json.
import PackageDescription

let package = Package(
    name: "T004NewOverloadWins",
    targets: [
        .target(name: "Core"),
        .target(name: "Billing", dependencies: ["Core"]),
        .target(name: "Reports", dependencies: ["Core"]),
        .testTarget(name: "BillingTests", dependencies: ["Billing"]),
        .testTarget(name: "ReportsTests", dependencies: ["Reports"]),
    ]
)
