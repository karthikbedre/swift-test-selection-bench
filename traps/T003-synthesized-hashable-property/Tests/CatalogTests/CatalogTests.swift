import XCTest
import Core
@testable import Catalog

final class CatalogTests: XCTestCase {
    func testDuplicatesCollapse() {
        XCTAssertEqual(Catalog.uniqueCount([Tag(name: "swift"), Tag(name: "swift")]), 1)
    }
}
