// swift-tools-version: 5.9
// Trap T001: a protocol extension supplies `description`, which string interpolation calls
// without anyone spelling it. BillingTests never names Formatter or description, yet it fails
// when the default changes. See trap.json for the edit and the test that must be selected.
import PackageDescription

let package = Package(
    name: "T001ProtocolDefaultDescription",
    targets: [
        .target(name: "Core"),
        .target(name: "Billing", dependencies: ["Core"]),
        .target(name: "Reports", dependencies: ["Core"]),
        .testTarget(name: "BillingTests", dependencies: ["Billing"]),
        .testTarget(name: "ReportsTests", dependencies: ["Reports"]),
    ]
)
