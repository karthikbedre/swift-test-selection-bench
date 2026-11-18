import XCTest
import Core
@testable import Storage

final class StoreTests: XCTestCase {
    func testSavedJSON() throws {
        XCTAssertEqual(try Store.save(Settings(theme: "dark")), #"{"theme":"dark"}"#)
    }
}
