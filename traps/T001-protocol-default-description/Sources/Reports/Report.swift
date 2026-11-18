import Core

public struct Report {
    public let opened: Clock
    public init(opened: Clock) { self.opened = opened }
    public var heading: String { "Opened at \(opened.hour)" }
}
