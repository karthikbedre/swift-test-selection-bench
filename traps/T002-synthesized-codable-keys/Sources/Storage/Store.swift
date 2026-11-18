import Core
import Foundation

public enum Store {
    public static func save(_ settings: Settings) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return String(decoding: try encoder.encode(settings), as: UTF8.self)
    }
}
