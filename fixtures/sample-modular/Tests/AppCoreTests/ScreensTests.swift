import XCTest
import Models
@testable import AppCore

final class ScreensTests: XCTestCase {
    func testTitles() {
        let titles = Screens.titles(character: .init(id: 1, name: "Rick"), episode: .init(code: "S01E02", title: "Lawnmower Dog"))
        XCTAssertEqual(titles, ["Rick #1", "S01E02: Lawnmower Dog"])
    }
}
