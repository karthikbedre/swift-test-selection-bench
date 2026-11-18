// swift-tools-version: 5.10
// Queries a compiler index store for the code that refers to a set of changed declarations.
// Build: swift build -c release --package-path tools/index-query
// The indexstore-db branch must match your toolchain: set INDEXSTORE_DB_BRANCH to the release branch
// for `swift --version` (for example release/6.0 for Swift 6.0.x). The default, main, suits the newest.
import Foundation
import PackageDescription

let indexStoreDBBranch = ProcessInfo.processInfo.environment["INDEXSTORE_DB_BRANCH"] ?? "main"

let package = Package(
    name: "index-query",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(url: "https://github.com/swiftlang/indexstore-db.git", branch: indexStoreDBBranch),
    ],
    targets: [
        .executableTarget(
            name: "index-query",
            dependencies: [.product(name: "IndexStoreDB", package: "indexstore-db")]
        ),
    ]
)
