import XCTest
import Core
@testable import Reports

final class ReportTests: XCTestCase {
    func testHeading() {
        XCTAssertEqual(Report(opened: Clock(hour: 9)).heading, "Opened at 9")
    }
}
