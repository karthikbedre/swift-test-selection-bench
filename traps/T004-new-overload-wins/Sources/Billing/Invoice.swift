import Core

public struct Invoice: Sendable {
    public let total: Int
    public init(total: Int) { self.total = total }
    public var line: String { render(total) }
}
