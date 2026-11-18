import XCTest
import Models
@testable import CharacterFeature

final class CharacterRowTests: XCTestCase {
    func testTitle() {
        XCTAssertEqual(CharacterRow(character: Character(id: 2, name: "Morty")).title, "Morty #2")
    }
}
