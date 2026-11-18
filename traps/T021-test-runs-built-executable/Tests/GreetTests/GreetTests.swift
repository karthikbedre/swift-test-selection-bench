import Foundation
import XCTest

final class GreetTests: XCTestCase {
    /// The folder that holds the built products, found from the test bundle.
    private var products: URL {
        Bundle(for: GreetTests.self).bundleURL.deletingLastPathComponent()
    }

    func testGreeting() throws {
        let process = Process()
        process.executableURL = products.appendingPathComponent("greet")
        process.arguments = ["Sam"]
        let pipe = Pipe()
        process.standardOutput = pipe
        try process.run()
        process.waitUntilExit()
        let output = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
        XCTAssertEqual(output, "Hello, Sam!\n")
    }
}
