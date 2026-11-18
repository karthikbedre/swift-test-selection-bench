public struct Episode: Equatable, Sendable {
    public let code: String
    public var title: String

    public init(code: String, title: String) {
        self.code = code
        self.title = title
    }
}

#if DEBUG
public enum EpisodeDebug {
    public static let sample = Episode(code: "S01E01", title: "Pilot")
}
#endif
