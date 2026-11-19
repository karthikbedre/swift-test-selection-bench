import XCTest
import Core
@testable import Reports

final class ReportTests: XCTestCase {
    func testHeading() {
        XCTAssertEqual(heading(Clock(hour: 9)), "Opened at 9")
    }
}
