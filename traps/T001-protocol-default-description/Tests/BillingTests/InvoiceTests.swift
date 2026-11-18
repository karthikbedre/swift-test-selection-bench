import XCTest
@testable import Billing

final class InvoiceTests: XCTestCase {
    func testSummaryLine() {
        let invoice = Invoice(number: "INV-7", total: 42)
        XCTAssertEqual("\(invoice)", "INV-7 | 42")
    }
}
