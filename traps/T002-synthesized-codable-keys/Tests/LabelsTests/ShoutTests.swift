import XCTest
import Core
@testable import Labels

final class ShoutTests: XCTestCase {
    func testShout() {
        XCTAssertEqual(shout(Label(text: "hi")), "HI")
    }
}
