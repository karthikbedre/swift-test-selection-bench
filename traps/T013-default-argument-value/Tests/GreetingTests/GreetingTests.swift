import XCTest
@testable import Greeting

final class GreetingTests: XCTestCase {
    func testWelcome() {
        XCTAssertEqual(welcome("Sam"), "Welcome, Sam!")
    }
}
