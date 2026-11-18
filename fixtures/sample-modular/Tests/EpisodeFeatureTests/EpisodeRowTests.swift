import XCTest
import Models
@testable import EpisodeFeature

final class EpisodeRowTests: XCTestCase {
    func testTitle() {
        XCTAssertEqual(EpisodeRow(episode: Episode(code: "S01E01", title: "Pilot")).title, "S01E01: Pilot")
    }
}
