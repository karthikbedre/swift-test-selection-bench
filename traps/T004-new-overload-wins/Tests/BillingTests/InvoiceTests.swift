import XCTest
@testable import Billing

final class InvoiceTests: XCTestCase {
    func testLine() {
        XCTAssertEqual(Invoice(total: 42).line, "value:42")
    }
}
