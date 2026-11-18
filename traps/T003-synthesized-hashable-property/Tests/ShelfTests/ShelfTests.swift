import XCTest
import Core
@testable import Shelf

final class ShelfTests: XCTestCase {
    func testCapacity() {
        XCTAssertEqual(capacity([Box(size: 2), Box(size: 3)]), 5)
    }
}
