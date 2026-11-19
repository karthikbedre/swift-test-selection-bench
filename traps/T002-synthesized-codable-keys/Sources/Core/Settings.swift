public struct Settings: Codable, Sendable {
    public var theme: String

    public init(theme: String) { self.theme = theme }

    enum CodingKeys: String, CodingKey {
        case theme = "theme"
    }
}
