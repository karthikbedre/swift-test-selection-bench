import XCTest
@testable import Models

final class CharacterTests: XCTestCase {
    func testDisplayName() {
        XCTAssertEqual(Character(id: 1, name: "Rick").displayName, "Rick #1")
    }
}
