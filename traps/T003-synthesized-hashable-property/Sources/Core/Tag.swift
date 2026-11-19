import Foundation

public struct Tag: Hashable, Sendable {
    public var name: String

    public init(name: String) { self.name = name }
}
