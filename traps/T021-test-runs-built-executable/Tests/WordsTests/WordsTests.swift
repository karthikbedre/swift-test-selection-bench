import XCTest
@testable import Words

final class WordsTests: XCTestCase {
    func testShout() {
        XCTAssertEqual(shout("hi"), "HI")
    }
}
